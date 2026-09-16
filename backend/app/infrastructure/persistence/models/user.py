import enum
from uuid import uuid4

from sqlalchemy import Column, String, Text, Boolean, Enum as SQLEnum, ForeignKey, Index, func, text
from sqlalchemy import Uuid as UUID

from app.infrastructure.persistence.base import DeclarativeBase, TimestampMixin


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    SUPERVISOR = "supervisor"   # não usado no MVP; mantido por compatibilidade com o ERP
    SELLER = "seller"           # não usado no MVP; mantido por compatibilidade com o ERP
    PROMOTER = "promoter"       # NOVO — o papel deste app


class User(DeclarativeBase, TimestampMixin):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    email = Column(String(255), nullable=False)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=True)
    phone = Column(String(30), nullable=True)
    role = Column(
        SQLEnum(UserRole, native_enum=True,
                values_callable=lambda x: [e.value for e in x]),
        default=UserRole.PROMOTER,
        nullable=False,
    )
    # O segundo papel de campo de quem acumula promotor e vendedor. `role` continua
    # sendo UM papel — é o que vai no token e o que o ERP conhece (Âncora 5) —, e
    # decide onde o login cai; este é o outro. Só promoter ↔ seller faz sentido.
    secondary_role = Column(
        SQLEnum(UserRole, native_enum=True,
                values_callable=lambda x: [e.value for e in x]),
        nullable=True,
    )
    is_active = Column(Boolean, default=True, nullable=False)
    avatar_url = Column(Text, nullable=True)

    @property
    def roles(self) -> set[str]:
        """Os papéis da pessoa, como conjunto — é por aqui que se autoriza."""
        roles = {self.role.value}
        if self.secondary_role:
            roles.add(self.secondary_role.value)
        return roles

    __table_args__ = (
        Index("idx_users_tenant_email", "tenant_id", "email"),
        Index("idx_users_email_lower", func.lower(text("email"))),
    )
