# Property Revenue Dashboard - Technical Investigation & Resolution

**Candidate:** Shiva  
**Target Repository:** [Base360-AI / New_devs_App](https://github.com/Base360-AI/New_devs_App)  
**Fork:** [Shiva7147 / New_devs_App](https://github.com/Shiva7147/New_devs_App)  
**Loom Walkthrough Video:** [Watch Walkthrough](LOOM_VIDEO_LINK_PLACEHOLDER)

---

## Executive Summary

An investigation was conducted into the three issues reported by clients and the finance team regarding the multi-tenant Property Revenue Dashboard:
1. **Client B (Ocean Rentals):** Cross-tenant data privacy leak on page refresh.
2. **Client A (Sunset Properties):** March revenue discrepancy ($1,250 missing).
3. **Finance Team:** Floating-point rounding drift of several cents across booking sums.

All three issues have been resolved following existing architectural patterns with zero destructive rewrites.

---

## 1. Issue: Cross-Tenant Data Leak on Page Refresh (Client B - Ocean Rentals)

### Symptoms
When logged in as Ocean Rentals (`ocean@propertyflow.com`), refreshing the dashboard occasionally displayed revenue figures belonging to Sunset Properties.

### Root Cause
1. **Cache Key Collision in `backend/app/services/cache.py`:**
   In `database/seed.sql`, both `tenant-a` (Sunset Properties) and `tenant-b` (Ocean Rentals) own properties with the identical ID `'prop-001'` (`Beach House Alpha` vs `Mountain Lodge Beta`).
   The caching layer in `cache.py` constructed cache keys solely based on property ID:
   ```python
   cache_key = f"revenue:{property_id}"
   ```
   Because `tenant_id` was omitted from the cache key namespace, whichever tenant queried `prop-001` first populated Redis under `revenue:prop-001`. Subsequent refreshes by the other tenant retrieved the cached payload across tenant boundaries.

2. **Attribute Access on Dictionary in `backend/app/api/v1/dashboard.py`:**
   The dashboard route extracted `tenant_id` via:
   ```python
   tenant_id = getattr(current_user, "tenant_id", "default_tenant") or "default_tenant"
   ```
   When `current_user` is a dictionary or when `tenant_id` was `None`, this collapsed to `"default_tenant"`, breaking tenant scoping.

### Solution
* **Namespace Cache Keys by Tenant:** Updated `cache.py` to:
  ```python
  cache_key = f"revenue:{tenant_id}:{property_id}"
  ```
* **Robust Tenant Extraction:** Added defensive checks in `dashboard.py` supporting both Pydantic auth models and dictionary contexts.

---

## 2. Issue: March Revenue Discrepancy (Client A - Sunset Properties)

### Symptoms
Sunset Properties' March revenue statements showed lower numbers than internal records.

### Root Cause
1. **Database Pool Failure:** The application was attempting to connect via an unconfigured pool setting in `database_pool.py`, silently falling back to a hardcoded mock data dictionary in `reservations.py` (`'prop-001': {'total': '1000.00', 'count': 3}`).
2. **Timezone Boundary Mismatch in Booking Timestamps:**
   In `database/seed.sql`, property `prop-001` (Beach House Alpha) is located in `Europe/Paris` (UTC+1).
   Reservation `res-tz-1` ($1,250.00) has check-in timestamp `2024-02-29 23:30:00+00` (UTC).
   In Paris local time (`Europe/Paris`), `23:30 UTC + 1 hour` is **`2024-03-01 00:30:00` (March 1st at 12:30 AM)**. The guest checked in on March 1st.
   Evaluating check-ins using naive UTC timestamps incorrectly pushed this booking into February, omitting $1,250.00 from March revenue.

### Solution
* **Direct Database Integration:** Implemented clean, asynchronous PostgreSQL querying using `asyncpg` in `backend/app/services/reservations.py`.
* **Local Timezone Normalization:** Evaluated reservation dates relative to the property's local timezone (`Europe/Paris`):
  ```sql
  EXTRACT(MONTH FROM (check_in_date AT TIME ZONE p.timezone)) = 3
  ```
  March revenue for `prop-001` now correctly reflects all 4 reservations totaling **$2,250.00** ($1,250 + $333.333 + $333.333 + $333.334).

---

## 3. Issue: Rounding & Cent Discrepancies (Finance Team)

### Symptoms
Revenue totals exhibited subtle drift of a few cents across aggregated bookings.

### Root Cause
Database fractional numeric amounts (e.g. `333.333`) were converted to native Python `float` before serialization in `dashboard.py`:
```python
total_revenue_float = float(revenue_data['total'])
```
IEEE 754 floating-point representations cause precision drift and rounding discrepancies when summed and formatted.

### Solution
Enforced Python's `Decimal` standard throughout calculation pipelines, quantizing with explicit `ROUND_HALF_UP` to two decimal places:
```python
total_dec = Decimal(str(revenue_data['total'])).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
```

---

## Verification & Live Proof

Automated verification tests confirm exact, isolated behavior:
```text
--- TESTING CLIENT A (Sunset Properties: sunset@propertyflow.com) ---
Tenant: tenant-a
Dashboard summary for prop-001:
  total_revenue: $2250.00
  reservations_count: 4
  Status: MATCHES INTERNAL RECORDS

--- TESTING CLIENT B (Ocean Rentals: ocean@propertyflow.com) ---
Tenant: tenant-b
Dashboard summary for prop-001:
  total_revenue: $0.00
  reservations_count: 0
  Status: ZERO CROSS-TENANT CONTAMINATION
```
