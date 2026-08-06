"""Importa todos os models para que o Alembic e o SQLAlchemy os registrem."""
from app.infrastructure.persistence.models.tenant import Tenant, TenantStatus  # noqa: F401
from app.infrastructure.persistence.models.user import User, UserRole  # noqa: F401
from app.infrastructure.persistence.models.customer import Customer, CustomerStatus  # noqa: F401
from app.infrastructure.persistence.models.product import Product  # noqa: F401
from app.infrastructure.persistence.models.promoter_customer import PromoterCustomer  # noqa: F401
from app.infrastructure.persistence.models.customer_product import CustomerProduct  # noqa: F401
from app.infrastructure.persistence.models.stock_visit import (  # noqa: F401
    StockVisit,
    StockVisitItem,
    StockVisitStatus,
)
