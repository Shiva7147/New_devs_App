from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any
from decimal import Decimal, ROUND_HALF_UP
from app.services.cache import get_revenue_summary
from app.core.auth import authenticate_request as get_current_user

router = APIRouter()

@router.get("/dashboard/summary")
async def get_dashboard_summary(
    property_id: str,
    current_user: Any = Depends(get_current_user)
) -> Dict[str, Any]:
    
    # Robust multi-tenant extraction supporting both AuthenticatedUser model and dict
    tenant_id = getattr(current_user, "tenant_id", None)
    if not tenant_id and isinstance(current_user, dict):
        tenant_id = current_user.get("tenant_id")
    if not tenant_id:
        tenant_id = "default_tenant"
    
    # Retrieve tenant-isolated revenue data
    revenue_data = await get_revenue_summary(property_id, tenant_id)
    
    # Accounting-precision rounding to eliminate floating point drift
    total_dec = Decimal(str(revenue_data.get('total', '0.00'))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    
    return {
        "property_id": revenue_data.get('property_id', property_id),
        "tenant_id": tenant_id,
        "total_revenue": float(total_dec),
        "total_formatted": f"{total_dec:.2f}",
        "currency": revenue_data.get('currency', 'USD'),
        "reservations_count": revenue_data.get('count', 0)
    }
