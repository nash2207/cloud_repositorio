for file in database/connection.py database/models.py database/repositories/topology_repository.py database/repositories/slice_repository.py database/repositories/network_resource_repository.py database/repositories/virtual_machine_repository.py database/repositories/vm_interface_repository.py database/repositories/user_repository.py database/repositories/project_repository.py database/repositories/project_member_repository.py database/repositories/image_repository.py auth/auth_manager.py auth/authorization.py users/user_manager.py users/keystone_user_service.py projects/project_manager.py projects/keystone_project_service.py images/image_manager.py images/glance_image_service.py placement/placement_engine.py placement/placement_manager.py placement/providers/nova_provider.py deployment/network_deployer.py deployment/vm_deployer.py slices/slice_manager.py common/admin_connection.py; do [ -f "$file" ] && echo -e "\n=== FILE: $file ===" && cat "$file"; done

=== FILE: database/connection.py ===
import os

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker


PROJECT_DIR = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
)

DATABASE_PATH = os.path.join(
    PROJECT_DIR,
    "orchestrator.db"
)

DATABASE_URL = "sqlite:///" + DATABASE_PATH


engine = create_engine(
    DATABASE_URL,
    connect_args={
        "check_same_thread": False
    },
    echo=False
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

Base = declarative_base()


def get_db_session():
    return SessionLocal()


def initialize_database():
    # Es obligatorio importar los modelos antes de create_all.
    from database import models  # noqa: F401

    Base.metadata.create_all(bind=engine)

    print("Base de datos inicializada correctamente.")
    print("Ruta:", DATABASE_PATH)
=== FILE: database/models.py ===
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from database.connection import Base


# ============================================================
# USUARIOS
# Roles globales:
# - superadmin
# - admin
# - user
# ============================================================

class User(Base):
    __tablename__ = "users"

    id = Column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    username = Column(
        String(128),
        unique=True,
        nullable=False,
    )

    keystone_user_id = Column(
        String(64),
        unique=True,
        nullable=True,
    )

    role = Column(
        String(20),
        nullable=False,
        default="user",
    )

    is_active = Column(
        Boolean,
        nullable=False,
        default=True,
    )

    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    # Proyectos de los que este usuario es propietario.
    projects = relationship(
        "Project",
        back_populates="owner",
    )

    # Membresías del usuario en proyectos.
    project_memberships = relationship(
        "ProjectMember",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    # Topologías propiedad del usuario.
    topologies = relationship(
        "Topology",
        back_populates="owner",
    )

    # Slices propiedad del usuario.
    slices = relationship(
        "Slice",
        back_populates="owner",
    )

    images = relationship(
        "ImageResource",
        back_populates="owner",
    )


# ============================================================
# PROYECTOS
# ============================================================

class Project(Base):
    __tablename__ = "projects"

    id = Column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    openstack_project_id = Column(
        String(64),
        unique=True,
        nullable=True,
    )

    name = Column(
        String(128),
        unique=True,
        nullable=False,
    )

    owner_user_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=True,
    )

    status = Column(
        String(32),
        nullable=False,
        default="ACTIVE",
    )

    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    owner = relationship(
        "User",
        back_populates="projects",
    )

    memberships = relationship(
        "ProjectMember",
        back_populates="project",
        cascade="all, delete-orphan",
    )

    topologies = relationship(
        "Topology",
        back_populates="project",
    )

    slices = relationship(
        "Slice",
        back_populates="project",
    )

    images = relationship(
        "ImageResource",
        back_populates="project",
    )

class ImageResource(Base):
    __tablename__ = "image_resources"

    id = Column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    openstack_image_id = Column(
        String(64),
        unique=True,
        nullable=False,
    )

    name = Column(
        String(128),
        nullable=False,
    )

    owner_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
    )

    # Se conserva para auditoría del proyecto desde el que fue cargada.
    # No se usa para filtrar visibilidad: el catálogo es global.
    project_id = Column(
        Integer,
        ForeignKey("projects.id"),
        nullable=False,
    )

    scope = Column(
        String(32),
        nullable=False,
        default="GLOBAL",
    )

    disk_format = Column(
        String(32),
        nullable=False,
    )

    container_format = Column(
        String(32),
        nullable=False,
        default="bare",
    )

    status = Column(
        String(32),
        nullable=False,
        default="QUEUED",
    )

    size_bytes = Column(
        Integer,
        nullable=True,
    )

    source_filename = Column(
        String(255),
        nullable=True,
    )

    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    owner = relationship(
        "User",
        back_populates="images",
    )

    project = relationship(
        "Project",
        back_populates="images",
    )

    __table_args__ = (
        UniqueConstraint(
            "name",
            name="uq_global_image_name",
        ),
    )


class ProjectMember(Base):
    __tablename__ = "project_members"

    id = Column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    project_id = Column(
        Integer,
        ForeignKey("projects.id"),
        nullable=False,
    )

    user_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
    )

    # Rol dentro del proyecto:
    # - admin
    # - user
    membership_role = Column(
        String(32),
        nullable=False,
        default="user",
    )

    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    project = relationship(
        "Project",
        back_populates="memberships",
    )

    user = relationship(
        "User",
        back_populates="project_memberships",
    )

    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "user_id",
            name="uq_project_member",
        ),
    )


# ============================================================
# TOPOLOGÍAS LÓGICAS
# Una topología todavía no tiene recursos reales en OpenStack.
# Estados:
# - DRAFT
# - READY
# - INVALID
# ============================================================

class Topology(Base):
    __tablename__ = "topologies"

    id = Column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    name = Column(
        String(128),
        nullable=False,
    )

    owner_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
    )

    project_id = Column(
        Integer,
        ForeignKey("projects.id"),
        nullable=False,
    )

    platform = Column(
        String(32),
        nullable=False,
        default="openstack",
    )

    topology_type = Column(
        String(32),
        nullable=False,
        default="custom",
    )

    status = Column(
        String(32),
        nullable=False,
        default="DRAFT",
    )

    topology_json = Column(
        Text,
        nullable=False,
    )

    topology_image = Column(
        String(255),
        nullable=True,
    )

    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    owner = relationship(
        "User",
        back_populates="topologies",
    )

    project = relationship(
        "Project",
        back_populates="topologies",
    )

    virtual_machines = relationship(
        "TopologyVM",
        back_populates="topology",
        cascade="all, delete-orphan",
    )

    networks = relationship(
        "TopologyNetwork",
        back_populates="topology",
        cascade="all, delete-orphan",
    )

    links = relationship(
        "TopologyLink",
        back_populates="topology",
        cascade="all, delete-orphan",
    )

    slices = relationship(
        "Slice",
        back_populates="topology",
    )

    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "owner_id",
            "name",
            name="uq_topology_project_owner_name",
        ),
    )


class TopologyVM(Base):
    __tablename__ = "topology_vms"

    id = Column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    topology_id = Column(
        Integer,
        ForeignKey("topologies.id"),
        nullable=False,
    )

    name = Column(
        String(128),
        nullable=False,
    )

    image_id = Column(
        String(64),
        nullable=False,
    )

    image_name = Column(
        String(128),
        nullable=True,
    )

    flavor_id = Column(
        String(64),
        nullable=False,
    )

    flavor_name = Column(
        String(128),
        nullable=True,
    )

    topology = relationship(
        "Topology",
        back_populates="virtual_machines",
    )

    __table_args__ = (
        UniqueConstraint(
            "topology_id",
            "name",
            name="uq_topology_vm_name",
        ),
    )


class TopologyNetwork(Base):
    __tablename__ = "topology_networks"

    id = Column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    topology_id = Column(
        Integer,
        ForeignKey("topologies.id"),
        nullable=False,
    )

    name = Column(
        String(128),
        nullable=False,
    )

    # Neutron elegirá el CIDR real al desplegar el slice.
    prefix_length = Column(
        Integer,
        nullable=False,
        default=29,
    )

    enable_dhcp = Column(
        Boolean,
        nullable=False,
        default=True,
    )

    topology = relationship(
        "Topology",
        back_populates="networks",
    )

    __table_args__ = (
        UniqueConstraint(
            "topology_id",
            "name",
            name="uq_topology_network_name",
        ),
    )


class TopologyLink(Base):
    __tablename__ = "topology_links"

    id = Column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    topology_id = Column(
        Integer,
        ForeignKey("topologies.id"),
        nullable=False,
    )

    source_vm = Column(
        String(128),
        nullable=False,
    )

    target_vm = Column(
        String(128),
        nullable=False,
    )

    topology = relationship(
        "Topology",
        back_populates="links",
    )

    __table_args__ = (
        UniqueConstraint(
            "topology_id",
            "source_vm",
            "target_vm",
            name="uq_topology_link",
        ),
    )


# ============================================================
# SLICES DESPLEGADOS
# Un slice se crea a partir de una topología READY.
#
# Estados:
# - PENDING
# - PLANNING
# - DEPLOYING_NETWORKS
# - DEPLOYING_VMS
# - RUNNING
# - UPDATING
# - PARTIAL
# - ERROR
# - DELETING
# - DELETED
# ============================================================

class Slice(Base):
    __tablename__ = "slices"

    id = Column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    name = Column(
        String(128),
        nullable=False,
    )

    topology_id = Column(
        Integer,
        ForeignKey("topologies.id"),
        nullable=False,
    )

    owner_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
    )

    project_id = Column(
        Integer,
        ForeignKey("projects.id"),
        nullable=False,
    )

    openstack_project_id = Column(
        String(64),
        nullable=True,
    )

    platform = Column(
        String(32),
        nullable=False,
        default="openstack",
    )

    status = Column(
        String(32),
        nullable=False,
        default="PENDING",
    )

    error_message = Column(
        Text,
        nullable=True,
    )

    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    topology = relationship(
        "Topology",
        back_populates="slices",
    )

    owner = relationship(
        "User",
        back_populates="slices",
    )

    project = relationship(
        "Project",
        back_populates="slices",
    )

    virtual_machines = relationship(
        "VirtualMachine",
        back_populates="slice",
        cascade="all, delete-orphan",
    )

    networks = relationship(
        "NetworkResource",
        back_populates="slice",
        cascade="all, delete-orphan",
    )

    links = relationship(
        "SliceLink",
        back_populates="slice",
        cascade="all, delete-orphan",
    )

    events = relationship(
        "DeploymentEvent",
        back_populates="slice",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "name",
            name="uq_slice_project_name",
        ),
    )


# ============================================================
# RECURSOS REALES DEL SLICE
# ============================================================

class VirtualMachineInterface(Base):
    __tablename__ = "virtual_machine_interfaces"

    id = Column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    virtual_machine_id = Column(
        Integer,
        ForeignKey("virtual_machines.id"),
        nullable=False,
    )

    network_resource_id = Column(
        Integer,
        ForeignKey("network_resources.id"),
        nullable=True,
    )

    openstack_port_id = Column(
        String(64),
        unique=True,
        nullable=False,
    )

    ip_address = Column(
        String(64),
        nullable=True,
    )

    mac_address = Column(
        String(64),
        nullable=True,
    )

    interface_index = Column(
        Integer,
        nullable=False,
        default=0,
    )

    interface_type = Column(
        String(32),
        nullable=False,
        default="TOPOLOGY",
    )

    status = Column(
        String(32),
        nullable=False,
        default="PENDING",
    )

    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    virtual_machine = relationship(
        "VirtualMachine",
        back_populates="interfaces",
    )

    network_resource = relationship(
        "NetworkResource",
        back_populates="interfaces",
    )

    __table_args__ = (
        UniqueConstraint(
            "virtual_machine_id",
            "interface_index",
            name="uq_vm_interface_index",
        ),
        UniqueConstraint(
            "virtual_machine_id",
            "network_resource_id",
            name="uq_vm_network_interface",
        ),
    )

class NetworkResource(Base):
    __tablename__ = "network_resources"

    id = Column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    slice_id = Column(
        Integer,
        ForeignKey("slices.id"),
        nullable=False,
    )

    name = Column(
        String(128),
        nullable=False,
    )

    # Identifica el enlace lógico normalizado, por ejemplo vm1--vm2.
    link_key = Column(
        String(255),
        nullable=False,
    )

    # Posición usada por el asignador automático de subredes.
    allocation_index = Column(
        Integer,
        nullable=False,
    )

    openstack_network_id = Column(
        String(64),
        unique=True,
        nullable=True,
    )

    openstack_subnet_id = Column(
        String(64),
        unique=True,
        nullable=True,
    )

    openstack_router_id = Column(
        String(64),
        nullable=True,
    )

    cidr = Column(
        String(64),
        nullable=False,
    )

    gateway = Column(
        String(64),
        nullable=True,
    )

    enable_dhcp = Column(
        Boolean,
        nullable=False,
        default=True,
    )

    status = Column(
        String(32),
        nullable=False,
        default="PENDING",
    )

    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    slice = relationship(
        "Slice",
        back_populates="networks",
    )

    interfaces = relationship(
        "VirtualMachineInterface",
        back_populates="network_resource",
        cascade="all, delete-orphan",
    )

    links = relationship(
        "SliceLink",
        back_populates="network_resource",
    )

    __table_args__ = (
        UniqueConstraint(
            "slice_id",
            "name",
            name="uq_slice_network_name",
        ),
        UniqueConstraint(
            "slice_id",
            "link_key",
            name="uq_slice_network_link_key",
        ),
        UniqueConstraint(
            "slice_id",
            "allocation_index",
            name="uq_slice_network_allocation",
        ),
    )


class SliceLink(Base):
    __tablename__ = "slice_links"

    id = Column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    slice_id = Column(
        Integer,
        ForeignKey("slices.id"),
        nullable=False,
    )

    network_resource_id = Column(
        Integer,
        ForeignKey("network_resources.id"),
        nullable=True,
    )

    source_vm = Column(
        String(128),
        nullable=False,
    )

    target_vm = Column(
        String(128),
        nullable=False,
    )

    source_port_id = Column(
        String(64),
        nullable=True,
    )

    target_port_id = Column(
        String(64),
        nullable=True,
    )

    status = Column(
        String(32),
        nullable=False,
        default="PENDING",
    )

    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    slice = relationship(
        "Slice",
        back_populates="links",
    )

    network_resource = relationship(
        "NetworkResource",
        back_populates="links",
    )

    __table_args__ = (
        UniqueConstraint(
            "slice_id",
            "source_vm",
            "target_vm",
            name="uq_slice_link",
        ),
    )


class DeploymentEvent(Base):
    __tablename__ = "deployment_events"

    id = Column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    slice_id = Column(
        Integer,
        ForeignKey("slices.id"),
        nullable=False,
    )

    module = Column(
        String(64),
        nullable=False,
    )

    action = Column(
        String(128),
        nullable=False,
    )

    status = Column(
        String(32),
        nullable=False,
    )

    message = Column(
        Text,
        nullable=True,
    )

    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    slice = relationship(
        "Slice",
        back_populates="events",
    )
=== FILE: database/repositories/topology_repository.py ===
import json

from database.connection import get_db_session
from database.models import (
    Slice,
    Topology,
    TopologyLink,
    TopologyNetwork,
    TopologyVM,
)


VALID_TOPOLOGY_STATUSES = (
    "DRAFT",
    "READY",
    "INVALID",
)


def _apply_visibility(
    query,
    owner_id,
    project_id,
    role,
):
    role = str(role).lower()

    if role == "superadmin":
        return query

    if role == "admin":
        return query.filter(
            Topology.project_id == project_id
        )

    if role == "user":
        return query.filter(
            Topology.project_id == project_id,
            Topology.owner_id == owner_id,
        )

    # Un rol desconocido no debe poder ver nada.
    return query.filter(Topology.id == -1)


def _serialize_summary(record):
    return {
        "id": record.id,
        "name": record.name,
        "owner_id": record.owner_id,
        "owner_username": (
            record.owner.username
            if record.owner is not None
            else None
        ),
        "project_id": record.project_id,
        "project_name": (
            record.project.name
            if record.project is not None
            else None
        ),
        "platform": record.platform,
        "topology_type": record.topology_type,
        "status": record.status,
        "topology_image": record.topology_image,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


def _save_children(
    session,
    topology_id,
    topology_data,
):
    vms = topology_data.get("vms", [])

    for vm_data in vms:
        image_data = vm_data.get("image", {})
        flavor_data = vm_data.get("flavor", {})

        if not vm_data.get("name"):
            raise ValueError(
                "Existe una VM sin nombre."
            )

        if not image_data.get("id"):
            raise ValueError(
                "La VM '{}' no tiene una imagen.".format(
                    vm_data["name"]
                )
            )

        if not flavor_data.get("id"):
            raise ValueError(
                "La VM '{}' no tiene un flavor.".format(
                    vm_data["name"]
                )
            )

        session.add(
            TopologyVM(
                topology_id=topology_id,
                name=vm_data["name"],
                image_id=image_data["id"],
                image_name=image_data.get("name"),
                flavor_id=flavor_data["id"],
                flavor_name=flavor_data.get("name"),
            )
        )

    network_data = topology_data.get(
        "network",
        {}
    )

    session.add(
        TopologyNetwork(
            topology_id=topology_id,
            name=network_data.get(
                "name",
                "logical-network"
            ),
            prefix_length=network_data.get(
                "prefix_length",
                28
            ),
            enable_dhcp=bool(
                network_data.get(
                    "enable_dhcp",
                    True
                )
            ),
        )
    )

    for link_data in topology_data.get("links", []):
        source = link_data.get("source")
        target = link_data.get("target")

        if not source or not target:
            raise ValueError(
                "Existe un enlace incompleto."
            )

        session.add(
            TopologyLink(
                topology_id=topology_id,
                source_vm=source,
                target_vm=target,
            )
        )


def create_topology(
    topology_data,
    owner_id,
    project_id,
):
    session = get_db_session()

    try:
        if owner_id is None:
            raise ValueError(
                "owner_id es obligatorio."
            )

        if project_id is None:
            raise ValueError(
                "project_id es obligatorio."
            )

        topology_name = str(
            topology_data.get(
                "topology_name",
                ""
            )
        ).strip()

        if not topology_name:
            raise ValueError(
                "El nombre de la topología es obligatorio."
            )

        duplicated = (
            session.query(Topology)
            .filter(
                Topology.name == topology_name,
                Topology.owner_id == owner_id,
                Topology.project_id == project_id,
            )
            .first()
        )

        if duplicated is not None:
            raise ValueError(
                "Ya existe una topología llamada '{}' "
                "para este usuario dentro del proyecto.".format(
                    topology_name
                )
            )

        topology_data["topology_name"] = topology_name
        topology_data["status"] = "DRAFT"

        record = Topology(
            name=topology_name,
            owner_id=owner_id,
            project_id=project_id,
            platform=topology_data.get(
                "platform",
                "openstack"
            ),
            topology_type=topology_data.get(
                "topology_type",
                "custom"
            ),
            status="DRAFT",
            topology_json=json.dumps(
                topology_data
            ),
            topology_image=topology_data.get(
                "topology_image"
            ),
        )

        session.add(record)
        session.flush()

        _save_children(
            session=session,
            topology_id=record.id,
            topology_data=topology_data,
        )

        session.commit()
        session.refresh(record)

        return _serialize_summary(record)

    except Exception:
        session.rollback()
        raise

    finally:
        session.close()


def list_topologies(
    owner_id,
    project_id,
    role,
):
    session = get_db_session()

    try:
        query = session.query(Topology)

        query = _apply_visibility(
            query=query,
            owner_id=owner_id,
            project_id=project_id,
            role=role,
        )

        records = (
            query
            .order_by(Topology.created_at.desc())
            .all()
        )

        return [
            _serialize_summary(record)
            for record in records
        ]

    finally:
        session.close()


def get_topology(
    topology_id,
    owner_id,
    project_id,
    role,
):
    session = get_db_session()

    try:
        query = session.query(Topology).filter(
            Topology.id == topology_id
        )

        query = _apply_visibility(
            query=query,
            owner_id=owner_id,
            project_id=project_id,
            role=role,
        )

        record = query.first()

        if record is None:
            return None

        result = _serialize_summary(record)

        result["topology_data"] = json.loads(
            record.topology_json
        )

        result["virtual_machines"] = [
            {
                "id": vm.id,
                "name": vm.name,
                "image_id": vm.image_id,
                "image_name": vm.image_name,
                "flavor_id": vm.flavor_id,
                "flavor_name": vm.flavor_name,
            }
            for vm in record.virtual_machines
        ]

        result["networks"] = [
            {
                "id": network.id,
                "name": network.name,
                "prefix_length": network.prefix_length,
                "enable_dhcp": bool(
                    network.enable_dhcp
                ),
            }
            for network in record.networks
        ]

        result["links"] = [
            {
                "id": link.id,
                "source": link.source_vm,
                "target": link.target_vm,
            }
            for link in record.links
        ]

        return result

    finally:
        session.close()


def update_topology(
    topology_id,
    topology_data,
    owner_id,
    project_id,
    role,
):
    session = get_db_session()

    try:
        query = session.query(Topology).filter(
            Topology.id == topology_id
        )

        query = _apply_visibility(
            query=query,
            owner_id=owner_id,
            project_id=project_id,
            role=role,
        )

        record = query.first()

        if record is None:
            raise ValueError(
                "La topología no existe o no tiene permisos."
            )

        topology_name = str(
            topology_data.get(
                "topology_name",
                ""
            )
        ).strip()

        if not topology_name:
            raise ValueError(
                "El nombre de la topología es obligatorio."
            )

        duplicated = (
            session.query(Topology)
            .filter(
                Topology.name == topology_name,
                Topology.owner_id == record.owner_id,
                Topology.project_id == record.project_id,
                Topology.id != topology_id,
            )
            .first()
        )

        if duplicated is not None:
            raise ValueError(
                "Ya existe otra topología con ese nombre."
            )

        topology_data["topology_name"] = topology_name
        topology_data["status"] = "DRAFT"

        record.name = topology_name
        record.platform = topology_data.get(
            "platform",
            "openstack"
        )
        record.topology_type = topology_data.get(
            "topology_type",
            "custom"
        )
        record.status = "DRAFT"
        record.topology_json = json.dumps(
            topology_data
        )
        record.topology_image = topology_data.get(
            "topology_image"
        )

        session.query(TopologyVM).filter(
            TopologyVM.topology_id == topology_id
        ).delete(
            synchronize_session=False
        )

        session.query(TopologyNetwork).filter(
            TopologyNetwork.topology_id == topology_id
        ).delete(
            synchronize_session=False
        )

        session.query(TopologyLink).filter(
            TopologyLink.topology_id == topology_id
        ).delete(
            synchronize_session=False
        )

        _save_children(
            session=session,
            topology_id=record.id,
            topology_data=topology_data,
        )

        session.commit()
        session.refresh(record)

        return _serialize_summary(record)

    except Exception:
        session.rollback()
        raise

    finally:
        session.close()


def update_topology_status(
    topology_id,
    status,
    owner_id,
    project_id,
    role,
):
    session = get_db_session()

    try:
        status = str(status).upper()

        if status not in VALID_TOPOLOGY_STATUSES:
            raise ValueError(
                "Estado inválido: '{}'.".format(
                    status
                )
            )

        query = session.query(Topology).filter(
            Topology.id == topology_id
        )

        query = _apply_visibility(
            query=query,
            owner_id=owner_id,
            project_id=project_id,
            role=role,
        )

        record = query.first()

        if record is None:
            raise ValueError(
                "La topología no existe o no tiene permisos."
            )

        record.status = status

        topology_data = json.loads(
            record.topology_json
        )

        topology_data["status"] = status

        record.topology_json = json.dumps(
            topology_data
        )

        session.commit()

        return True

    except Exception:
        session.rollback()
        raise

    finally:
        session.close()


def delete_topology(
    topology_id,
    owner_id,
    project_id,
    role,
):
    session = get_db_session()

    try:
        query = session.query(Topology).filter(
            Topology.id == topology_id
        )

        query = _apply_visibility(
            query=query,
            owner_id=owner_id,
            project_id=project_id,
            role=role,
        )

        record = query.first()

        if record is None:
            return False

        associated_slices = (
            session.query(Slice)
            .filter(
                Slice.topology_id == topology_id
            )
            .count()
        )

        if associated_slices:
            raise ValueError(
                "La topología tiene {} slice(s) asociados. "
                "Primero debe eliminar esos slices.".format(
                    associated_slices
                )
            )

        session.delete(record)
        session.commit()

        return True

    except Exception:
        session.rollback()
        raise

    finally:
        session.close()
=== FILE: database/repositories/slice_repository.py ===
from database.connection import get_db_session
from database.models import (
    Slice,
    Topology,
)


VALID_SLICE_STATUSES = (
    "PENDING",
    "PLANNING",
    "DEPLOYING_NETWORKS",
    "DEPLOYING_VMS",
    "RUNNING",
    "UPDATING",
    "PARTIAL",
    "ERROR",
    "DELETING",
    "DELETED",
)


def serialize_slice(record):
    return {
        "id": record.id,
        "name": record.name,
        "topology_id": record.topology_id,
        "topology_name": (
            record.topology.name
            if record.topology is not None
            else None
        ),
        "owner_id": record.owner_id,
        "owner_username": (
            record.owner.username
            if record.owner is not None
            else None
        ),
        "project_id": record.project_id,
        "project_name": (
            record.project.name
            if record.project is not None
            else None
        ),
        "openstack_project_id":
            record.openstack_project_id,
        "platform": record.platform,
        "status": record.status,
        "error_message": record.error_message,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


def create_slice_record(
    name,
    topology_id,
    owner_id,
    project_id,
    openstack_project_id,
    platform="openstack",
):
    session = get_db_session()

    try:
        name = str(name).strip()

        if not name:
            raise ValueError(
                "El nombre del slice es obligatorio."
            )

        topology = session.query(
            Topology
        ).get(topology_id)

        if topology is None:
            raise ValueError(
                "La topología no existe."
            )

        if str(topology.status).upper() != "READY":
            raise ValueError(
                "Solo se pueden desplegar topologías READY."
            )

        if topology.project_id != project_id:
            raise ValueError(
                "La topología no pertenece al proyecto indicado."
            )

        duplicated = (
            session.query(Slice)
            .filter(
                Slice.project_id == project_id,
                Slice.name == name,
            )
            .first()
        )

        if duplicated is not None:
            raise ValueError(
                "Ya existe un slice llamado '{}' "
                "en este proyecto.".format(name)
            )

        record = Slice(
            name=name,
            topology_id=topology_id,
            owner_id=owner_id,
            project_id=project_id,
            openstack_project_id=openstack_project_id,
            platform=platform,
            status="PENDING",
            error_message=None,
        )

        session.add(record)
        session.commit()
        session.refresh(record)

        return serialize_slice(
            record
        )

    except Exception:
        session.rollback()
        raise

    finally:
        session.close()


def get_slice_by_id(
    slice_id,
):
    session = get_db_session()

    try:
        record = session.query(
            Slice
        ).get(slice_id)

        if record is None:
            return None

        return serialize_slice(
            record
        )

    finally:
        session.close()


def get_slice_by_name(
    name,
    project_id=None,
):
    session = get_db_session()

    try:
        query = session.query(
            Slice
        ).filter(
            Slice.name == name
        )

        if project_id is not None:
            query = query.filter(
                Slice.project_id == project_id
            )

        record = query.first()

        if record is None:
            return None

        return serialize_slice(
            record
        )

    finally:
        session.close()


def list_slice_records(
    owner_id=None,
    project_id=None,
    role="user",
    include_deleted=False,
):
    session = get_db_session()

    try:
        query = session.query(
            Slice
        )

        role = str(role).strip().lower()

        if role == "superadmin":
            pass

        elif role == "admin":
            query = query.filter(
                Slice.project_id == project_id
            )

        elif role == "user":
            query = query.filter(
                Slice.project_id == project_id,
                Slice.owner_id == owner_id,
            )

        else:
            return []

        if not include_deleted:
            query = query.filter(
                Slice.status != "DELETED"
            )

        records = (
            query
            .order_by(
                Slice.created_at.desc()
            )
            .all()
        )

        return [
            serialize_slice(record)
            for record in records
        ]

    finally:
        session.close()


def update_slice_status(
    slice_id,
    status,
    error_message=None,
):
    session = get_db_session()

    try:
        normalized_status = str(
            status
        ).strip().upper()

        if normalized_status not in VALID_SLICE_STATUSES:
            raise ValueError(
                "Estado de slice inválido: {}".format(
                    normalized_status
                )
            )

        record = session.query(
            Slice
        ).get(slice_id)

        if record is None:
            raise ValueError(
                "El slice no existe."
            )

        record.status = normalized_status
        record.error_message = error_message

        session.commit()
        session.refresh(record)

        return serialize_slice(
            record
        )

    except Exception:
        session.rollback()
        raise

    finally:
        session.close()


def delete_slice_record(
    slice_id,
):
    session = get_db_session()

    try:
        record = session.query(
            Slice
        ).get(slice_id)

        if record is None:
            return False

        session.delete(record)
        session.commit()

        return True

    except Exception:
        session.rollback()
        raise

    finally:
        session.close()
=== FILE: database/repositories/network_resource_repository.py ===
from database.connection import get_db_session
from database.models import (
    NetworkResource,
    Slice,
    SliceLink,
)


def serialize_network_resource(record):
    return {
        "id": record.id,
        "slice_id": record.slice_id,
        "name": record.name,
        "link_key": record.link_key,
        "allocation_index": record.allocation_index,
        "openstack_network_id":
            record.openstack_network_id,
        "openstack_subnet_id":
            record.openstack_subnet_id,
        "openstack_router_id":
            record.openstack_router_id,
        "cidr": record.cidr,
        "gateway": record.gateway,
        "enable_dhcp": record.enable_dhcp,
        "status": record.status,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


def serialize_slice_link(record):
    return {
        "id": record.id,
        "slice_id": record.slice_id,
        "network_resource_id":
            record.network_resource_id,
        "source_vm": record.source_vm,
        "target_vm": record.target_vm,
        "source_port_id": record.source_port_id,
        "target_port_id": record.target_port_id,
        "status": record.status,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


def create_network_resource_record(
    slice_id,
    name,
    link_key,
    allocation_index,
    cidr,
    gateway,
    enable_dhcp=True,
    status="PENDING",
):
    session = get_db_session()

    try:
        slice_record = session.query(
            Slice
        ).get(slice_id)

        if slice_record is None:
            raise ValueError(
                "El slice no existe."
            )

        duplicated_name = (
            session.query(NetworkResource)
            .filter(
                NetworkResource.slice_id == slice_id,
                NetworkResource.name == name,
            )
            .first()
        )

        if duplicated_name is not None:
            raise ValueError(
                "Ya existe una red con ese nombre "
                "dentro del slice."
            )

        duplicated_link = (
            session.query(NetworkResource)
            .filter(
                NetworkResource.slice_id == slice_id,
                NetworkResource.link_key == link_key,
            )
            .first()
        )

        if duplicated_link is not None:
            raise ValueError(
                "Ya existe una red para el enlace '{}'."
                .format(link_key)
            )

        duplicated_index = (
            session.query(NetworkResource)
            .filter(
                NetworkResource.slice_id == slice_id,
                NetworkResource.allocation_index
                == allocation_index,
            )
            .first()
        )

        if duplicated_index is not None:
            raise ValueError(
                "El índice de asignación ya está en uso."
            )

        record = NetworkResource(
            slice_id=slice_id,
            name=name,
            link_key=link_key,
            allocation_index=allocation_index,
            cidr=cidr,
            gateway=gateway,
            enable_dhcp=enable_dhcp,
            status=str(status).upper(),
        )

        session.add(record)
        session.commit()
        session.refresh(record)

        return serialize_network_resource(
            record
        )

    except Exception:
        session.rollback()
        raise

    finally:
        session.close()


def get_network_resource_by_id(
    network_resource_id,
):
    session = get_db_session()

    try:
        record = session.query(
            NetworkResource
        ).get(network_resource_id)

        if record is None:
            return None

        return serialize_network_resource(
            record
        )

    finally:
        session.close()


def get_network_resource_by_link_key(
    slice_id,
    link_key,
):
    session = get_db_session()

    try:
        record = (
            session.query(NetworkResource)
            .filter(
                NetworkResource.slice_id == slice_id,
                NetworkResource.link_key == link_key,
            )
            .first()
        )

        if record is None:
            return None

        return serialize_network_resource(
            record
        )

    finally:
        session.close()


def list_network_resources(
    slice_id,
):
    session = get_db_session()

    try:
        records = (
            session.query(NetworkResource)
            .filter(
                NetworkResource.slice_id == slice_id
            )
            .order_by(
                NetworkResource.allocation_index.asc()
            )
            .all()
        )

        return [
            serialize_network_resource(record)
            for record in records
        ]

    finally:
        session.close()


def update_network_resource_openstack(
    network_resource_id,
    openstack_network_id=None,
    openstack_subnet_id=None,
    openstack_router_id=None,
    status=None,
):
    session = get_db_session()

    try:
        record = session.query(
            NetworkResource
        ).get(network_resource_id)

        if record is None:
            raise ValueError(
                "El recurso de red no existe."
            )

        if openstack_network_id is not None:
            record.openstack_network_id = (
                openstack_network_id
            )

        if openstack_subnet_id is not None:
            record.openstack_subnet_id = (
                openstack_subnet_id
            )

        if openstack_router_id is not None:
            record.openstack_router_id = (
                openstack_router_id
            )

        if status is not None:
            record.status = str(
                status
            ).upper()

        session.commit()
        session.refresh(record)

        return serialize_network_resource(
            record
        )

    except Exception:
        session.rollback()
        raise

    finally:
        session.close()


def update_network_resource_status(
    network_resource_id,
    status,
):
    return update_network_resource_openstack(
        network_resource_id=network_resource_id,
        status=status,
    )


def create_slice_link_record(
    slice_id,
    network_resource_id,
    source_vm,
    target_vm,
    source_port_id=None,
    target_port_id=None,
    status="PENDING",
):
    session = get_db_session()

    try:
        network_record = session.query(
            NetworkResource
        ).get(network_resource_id)

        if network_record is None:
            raise ValueError(
                "El recurso de red no existe."
            )

        if network_record.slice_id != slice_id:
            raise ValueError(
                "La red no pertenece al slice indicado."
            )

        duplicated = (
            session.query(SliceLink)
            .filter(
                SliceLink.slice_id == slice_id,
                SliceLink.source_vm == source_vm,
                SliceLink.target_vm == target_vm,
            )
            .first()
        )

        if duplicated is not None:
            raise ValueError(
                "El enlace ya se encuentra registrado."
            )

        record = SliceLink(
            slice_id=slice_id,
            network_resource_id=network_resource_id,
            source_vm=source_vm,
            target_vm=target_vm,
            source_port_id=source_port_id,
            target_port_id=target_port_id,
            status=str(status).upper(),
        )

        session.add(record)
        session.commit()
        session.refresh(record)

        return serialize_slice_link(
            record
        )

    except Exception:
        session.rollback()
        raise

    finally:
        session.close()


def update_slice_link_ports(
    slice_link_id,
    source_port_id,
    target_port_id,
    status="ACTIVE",
):
    session = get_db_session()

    try:
        record = session.query(
            SliceLink
        ).get(slice_link_id)

        if record is None:
            raise ValueError(
                "El enlace del slice no existe."
            )

        record.source_port_id = source_port_id
        record.target_port_id = target_port_id
        record.status = str(status).upper()

        session.commit()
        session.refresh(record)

        return serialize_slice_link(
            record
        )

    except Exception:
        session.rollback()
        raise

    finally:
        session.close()


def list_slice_links(
    slice_id,
):
    session = get_db_session()

    try:
        records = (
            session.query(SliceLink)
            .filter(
                SliceLink.slice_id == slice_id
            )
            .order_by(SliceLink.id.asc())
            .all()
        )

        return [
            serialize_slice_link(record)
            for record in records
        ]

    finally:
        session.close()


def delete_slice_link_record(
    slice_link_id,
):
    session = get_db_session()

    try:
        record = session.query(
            SliceLink
        ).get(slice_link_id)

        if record is None:
            return False

        session.delete(record)
        session.commit()

        return True

    except Exception:
        session.rollback()
        raise

    finally:
        session.close()


def delete_network_resource_record(
    network_resource_id,
):
    session = get_db_session()

    try:
        record = session.query(
            NetworkResource
        ).get(network_resource_id)

        if record is None:
            return False

        session.delete(record)
        session.commit()

        return True

    except Exception:
        session.rollback()
        raise

    finally:
        session.close()
=== FILE: database/repositories/virtual_machine_repository.py ===
from database.connection import get_db_session
from database.models import (
    Slice,
    VirtualMachine,
)


VALID_VM_STATUSES = (
    "PENDING",
    "BUILD",
    "ACTIVE",
    "ERROR",
    "DELETING",
    "DELETED",
)


def serialize_virtual_machine(record):
    return {
        "id": record.id,
        "slice_id": record.slice_id,
        "name": record.name,
        "openstack_server_id":
            record.openstack_server_id,
        "image_id": record.image_id,
        "flavor_id": record.flavor_id,
        "worker": record.worker,
        "availability_zone":
            record.availability_zone,
        "status": record.status,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


def create_virtual_machine_record(
    slice_id,
    name,
    image_id,
    flavor_id,
    worker=None,
    availability_zone=None,
    status="PENDING",
):
    session = get_db_session()

    try:
        slice_record = session.query(
            Slice
        ).get(slice_id)

        if slice_record is None:
            raise ValueError(
                "El slice no existe."
            )

        name = str(name).strip()

        if not name:
            raise ValueError(
                "El nombre de la VM es obligatorio."
            )

        duplicated = (
            session.query(VirtualMachine)
            .filter(
                VirtualMachine.slice_id == slice_id,
                VirtualMachine.name == name,
            )
            .first()
        )

        if duplicated is not None:
            raise ValueError(
                "Ya existe la VM '{}' en el slice."
                .format(name)
            )

        normalized_status = str(
            status
        ).strip().upper()

        if normalized_status not in VALID_VM_STATUSES:
            raise ValueError(
                "Estado de VM inválido."
            )

        record = VirtualMachine(
            slice_id=slice_id,
            name=name,
            image_id=image_id,
            flavor_id=flavor_id,
            worker=worker,
            availability_zone=availability_zone,
            status=normalized_status,
        )

        session.add(record)
        session.commit()
        session.refresh(record)

        return serialize_virtual_machine(
            record
        )

    except Exception:
        session.rollback()
        raise

    finally:
        session.close()


def get_virtual_machine_by_id(
    virtual_machine_id,
):
    session = get_db_session()

    try:
        record = session.query(
            VirtualMachine
        ).get(virtual_machine_id)

        if record is None:
            return None

        return serialize_virtual_machine(
            record
        )

    finally:
        session.close()


def get_virtual_machine_by_name(
    slice_id,
    name,
):
    session = get_db_session()

    try:
        record = (
            session.query(VirtualMachine)
            .filter(
                VirtualMachine.slice_id == slice_id,
                VirtualMachine.name == name,
            )
            .first()
        )

        if record is None:
            return None

        return serialize_virtual_machine(
            record
        )

    finally:
        session.close()


def list_virtual_machines(
    slice_id,
):
    session = get_db_session()

    try:
        records = (
            session.query(VirtualMachine)
            .filter(
                VirtualMachine.slice_id == slice_id
            )
            .order_by(
                VirtualMachine.name.asc()
            )
            .all()
        )

        return [
            serialize_virtual_machine(record)
            for record in records
        ]

    finally:
        session.close()


def update_virtual_machine_openstack(
    virtual_machine_id,
    openstack_server_id=None,
    worker=None,
    availability_zone=None,
    status=None,
):
    session = get_db_session()

    try:
        record = session.query(
            VirtualMachine
        ).get(virtual_machine_id)

        if record is None:
            raise ValueError(
                "La máquina virtual no existe."
            )

        if openstack_server_id is not None:
            record.openstack_server_id = (
                openstack_server_id
            )

        if worker is not None:
            record.worker = worker

        if availability_zone is not None:
            record.availability_zone = (
                availability_zone
            )

        if status is not None:
            normalized_status = str(
                status
            ).strip().upper()

            if (
                normalized_status
                not in VALID_VM_STATUSES
            ):
                raise ValueError(
                    "Estado de VM inválido: {}."
                    .format(normalized_status)
                )

            record.status = normalized_status

        session.commit()
        session.refresh(record)

        return serialize_virtual_machine(
            record
        )

    except Exception:
        session.rollback()
        raise

    finally:
        session.close()


def update_virtual_machine_status(
    virtual_machine_id,
    status,
):
    return update_virtual_machine_openstack(
        virtual_machine_id=virtual_machine_id,
        status=status,
    )


def delete_virtual_machine_record(
    virtual_machine_id,
):
    session = get_db_session()

    try:
        record = session.query(
            VirtualMachine
        ).get(virtual_machine_id)

        if record is None:
            return False

        session.delete(record)
        session.commit()

        return True

    except Exception:
        session.rollback()
        raise

    finally:
        session.close()
=== FILE: database/repositories/vm_interface_repository.py ===
from database.connection import get_db_session
from database.models import (
    NetworkResource,
    VirtualMachine,
    VirtualMachineInterface,
)


VALID_INTERFACE_STATUSES = (
    "PENDING",
    "DOWN",
    "ACTIVE",
    "ERROR",
    "DELETED",
)


def serialize_vm_interface(record):
    return {
        "id": record.id,
        "virtual_machine_id":
            record.virtual_machine_id,
        "network_resource_id":
            record.network_resource_id,
        "openstack_port_id":
            record.openstack_port_id,
        "ip_address": record.ip_address,
        "mac_address": record.mac_address,
        "interface_index":
            record.interface_index,
        "status": record.status,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


def create_vm_interface_record(
    virtual_machine_id,
    network_resource_id,
    openstack_port_id,
    interface_index,
    ip_address=None,
    mac_address=None,
    status="PENDING",
):
    session = get_db_session()

    try:
        vm_record = session.query(
            VirtualMachine
        ).get(virtual_machine_id)

        if vm_record is None:
            raise ValueError(
                "La máquina virtual no existe."
            )

        network_record = session.query(
            NetworkResource
        ).get(network_resource_id)

        if network_record is None:
            raise ValueError(
                "El recurso de red no existe."
            )

        if (
            vm_record.slice_id
            != network_record.slice_id
        ):
            raise ValueError(
                "La VM y la red no pertenecen "
                "al mismo slice."
            )

        duplicated_port = (
            session.query(VirtualMachineInterface)
            .filter(
                VirtualMachineInterface.openstack_port_id
                == openstack_port_id
            )
            .first()
        )

        if duplicated_port is not None:
            raise ValueError(
                "El puerto ya está registrado."
            )

        duplicated_index = (
            session.query(VirtualMachineInterface)
            .filter(
                VirtualMachineInterface.virtual_machine_id
                == virtual_machine_id,
                VirtualMachineInterface.interface_index
                == interface_index,
            )
            .first()
        )

        if duplicated_index is not None:
            raise ValueError(
                "El índice de interfaz ya está utilizado."
            )

        normalized_status = str(
            status
        ).strip().upper()

        if (
            normalized_status
            not in VALID_INTERFACE_STATUSES
        ):
            raise ValueError(
                "Estado de interfaz inválido."
            )

        record = VirtualMachineInterface(
            virtual_machine_id=virtual_machine_id,
            network_resource_id=network_resource_id,
            openstack_port_id=openstack_port_id,
            ip_address=ip_address,
            mac_address=mac_address,
            interface_index=interface_index,
            status=normalized_status,
        )

        session.add(record)
        session.commit()
        session.refresh(record)

        return serialize_vm_interface(
            record
        )

    except Exception:
        session.rollback()
        raise

    finally:
        session.close()


def list_vm_interfaces(
    virtual_machine_id,
):
    session = get_db_session()

    try:
        records = (
            session.query(VirtualMachineInterface)
            .filter(
                VirtualMachineInterface.virtual_machine_id
                == virtual_machine_id
            )
            .order_by(
                VirtualMachineInterface.interface_index.asc()
            )
            .all()
        )

        return [
            serialize_vm_interface(record)
            for record in records
        ]

    finally:
        session.close()


def list_slice_interfaces(
    slice_id,
):
    session = get_db_session()

    try:
        records = (
            session.query(VirtualMachineInterface)
            .join(
                VirtualMachine,
                VirtualMachine.id
                == VirtualMachineInterface.virtual_machine_id,
            )
            .filter(
                VirtualMachine.slice_id == slice_id
            )
            .order_by(
                VirtualMachine.name.asc(),
                VirtualMachineInterface.interface_index.asc(),
            )
            .all()
        )

        return [
            serialize_vm_interface(record)
            for record in records
        ]

    finally:
        session.close()


def update_vm_interface(
    interface_id,
    ip_address=None,
    mac_address=None,
    status=None,
):
    session = get_db_session()

    try:
        record = session.query(
            VirtualMachineInterface
        ).get(interface_id)

        if record is None:
            raise ValueError(
                "La interfaz no existe."
            )

        if ip_address is not None:
            record.ip_address = ip_address

        if mac_address is not None:
            record.mac_address = mac_address

        if status is not None:
            normalized_status = str(
                status
            ).strip().upper()

            if (
                normalized_status
                not in VALID_INTERFACE_STATUSES
            ):
                raise ValueError(
                    "Estado de interfaz inválido."
                )

            record.status = normalized_status

        session.commit()
        session.refresh(record)

        return serialize_vm_interface(
            record
        )

    except Exception:
        session.rollback()
        raise

    finally:
        session.close()


def delete_vm_interface_record(
    interface_id,
):
    session = get_db_session()

    try:
        record = session.query(
            VirtualMachineInterface
        ).get(interface_id)

        if record is None:
            return False

        session.delete(record)
        session.commit()

        return True

    except Exception:
        session.rollback()
        raise

    finally:
        session.close()
=== FILE: database/repositories/user_repository.py ===
from database.connection import get_db_session
from database.models import (
    Project,
    ProjectMember,
    Slice,
    Topology,
    User,
)


VALID_ROLES = (
    "superadmin",
    "admin",
    "user",
)


def serialize_user(record):
    return {
        "id": record.id,
        "keystone_user_id": record.keystone_user_id,
        "username": record.username,
        "role": record.role.lower(),
        "is_active": record.is_active,
        "created_at": record.created_at,
    }


def create_user(
    username,
    keystone_user_id,
    role="user",
):
    session = get_db_session()

    try:
        username = username.strip()
        role = role.strip().lower()

        if not username:
            raise ValueError(
                "El nombre del usuario es obligatorio."
            )

        if not keystone_user_id:
            raise ValueError(
                "El Keystone User ID es obligatorio."
            )

        if role not in VALID_ROLES:
            raise ValueError(
                "Rol inválido: '{}'. Roles permitidos: {}.".format(
                    role,
                    ", ".join(VALID_ROLES),
                )
            )

        existing_username = (
            session.query(User)
            .filter(User.username == username)
            .first()
        )

        if existing_username is not None:
            raise ValueError(
                "Ya existe el usuario '{}'.".format(username)
            )

        existing_keystone = (
            session.query(User)
            .filter(
                User.keystone_user_id == keystone_user_id
            )
            .first()
        )

        if existing_keystone is not None:
            raise ValueError(
                "El usuario de Keystone ya está registrado."
            )

        record = User(
            username=username,
            keystone_user_id=keystone_user_id,
            role=role,
            is_active=True,
        )

        session.add(record)
        session.commit()
        session.refresh(record)

        return serialize_user(record)

    except Exception:
        session.rollback()
        raise

    finally:
        session.close()


def get_or_create_user(
    keystone_user_id,
    username,
    default_role="user",
):
    session = get_db_session()

    try:
        username = username.strip()
        default_role = default_role.strip().lower()

        if not keystone_user_id:
            raise ValueError(
                "El Keystone User ID es obligatorio."
            )

        if not username:
            raise ValueError(
                "El nombre del usuario es obligatorio."
            )

        if default_role not in VALID_ROLES:
            raise ValueError(
                "Rol por defecto inválido."
            )

        record = (
            session.query(User)
            .filter(
                User.keystone_user_id == keystone_user_id
            )
            .first()
        )

        if record is not None:
            return serialize_user(record)

        existing_username = (
            session.query(User)
            .filter(User.username == username)
            .first()
        )

        if existing_username is not None:
            existing_username.keystone_user_id = (
                keystone_user_id
            )

            session.commit()
            session.refresh(existing_username)

            return serialize_user(existing_username)

        record = User(
            username=username,
            keystone_user_id=keystone_user_id,
            role=default_role,
            is_active=True,
        )

        session.add(record)
        session.commit()
        session.refresh(record)

        return serialize_user(record)

    except Exception:
        session.rollback()
        raise

    finally:
        session.close()


def get_user_by_id(user_id):
    session = get_db_session()

    try:
        record = session.query(User).get(user_id)

        if record is None:
            return None

        return serialize_user(record)

    finally:
        session.close()


def get_user_by_keystone_id(keystone_user_id):
    session = get_db_session()

    try:
        record = (
            session.query(User)
            .filter(
                User.keystone_user_id == keystone_user_id
            )
            .first()
        )

        if record is None:
            return None

        return serialize_user(record)

    finally:
        session.close()


def get_user_by_username(username):
    session = get_db_session()

    try:
        record = (
            session.query(User)
            .filter(
                User.username == username.strip()
            )
            .first()
        )

        if record is None:
            return None

        return serialize_user(record)

    finally:
        session.close()


def user_exists(username):
    session = get_db_session()

    try:
        return (
            session.query(User)
            .filter(
                User.username == username.strip()
            )
            .count()
            > 0
        )

    finally:
        session.close()


def list_all_users():
    session = get_db_session()

    try:
        records = (
            session.query(User)
            .order_by(User.username.asc())
            .all()
        )

        return [
            serialize_user(record)
            for record in records
        ]

    finally:
        session.close()


def list_users_visible_to_admin(admin_user_id):
    """
    Devuelve los usuarios pertenecientes a proyectos donde
    admin_user_id tiene membership_role='admin'.
    """

    session = get_db_session()

    try:
        admin_project_ids = [
            membership.project_id
            for membership in (
                session.query(ProjectMember)
                .filter(
                    ProjectMember.user_id == admin_user_id,
                    ProjectMember.membership_role == "admin",
                )
                .all()
            )
        ]

        if not admin_project_ids:
            return []

        records = (
            session.query(User)
            .join(
                ProjectMember,
                ProjectMember.user_id == User.id,
            )
            .filter(
                ProjectMember.project_id.in_(
                    admin_project_ids
                )
            )
            .distinct()
            .order_by(User.username.asc())
            .all()
        )

        return [
            serialize_user(record)
            for record in records
        ]

    finally:
        session.close()


def update_user(
    user_id,
    username=None,
    role=None,
    keystone_user_id=None,
):
    session = get_db_session()

    try:
        record = session.query(User).get(user_id)

        if record is None:
            raise ValueError(
                "El usuario no existe."
            )

        if username is not None:
            username = username.strip()

            if not username:
                raise ValueError(
                    "El nombre del usuario no puede estar vacío."
                )

            if username != record.username:
                duplicated_username = (
                    session.query(User)
                    .filter(
                        User.username == username,
                        User.id != user_id,
                    )
                    .first()
                )

                if duplicated_username is not None:
                    raise ValueError(
                        "Ya existe otro usuario con ese nombre."
                    )

                record.username = username

        if role is not None:
            role = role.strip().lower()

            if role not in VALID_ROLES:
                raise ValueError(
                    "Rol inválido: '{}'. Roles permitidos: {}.".format(
                        role,
                        ", ".join(VALID_ROLES),
                    )
                )

            record.role = role

        if keystone_user_id is not None:
            keystone_user_id = keystone_user_id.strip()

            if not keystone_user_id:
                raise ValueError(
                    "El Keystone User ID no puede estar vacío."
                )

            if (
                keystone_user_id
                != record.keystone_user_id
            ):
                duplicated_keystone = (
                    session.query(User)
                    .filter(
                        User.keystone_user_id
                        == keystone_user_id,
                        User.id != user_id,
                    )
                    .first()
                )

                if duplicated_keystone is not None:
                    raise ValueError(
                        "Ese Keystone User ID ya está registrado."
                    )

                record.keystone_user_id = (
                    keystone_user_id
                )

        session.commit()
        session.refresh(record)

        return serialize_user(record)

    except Exception:
        session.rollback()
        raise

    finally:
        session.close()


def update_user_status(
    user_id,
    is_active,
):
    session = get_db_session()

    try:
        record = session.query(User).get(user_id)

        if record is None:
            raise ValueError(
                "El usuario no existe."
            )

        record.is_active = bool(is_active)

        session.commit()
        session.refresh(record)

        return serialize_user(record)

    except Exception:
        session.rollback()
        raise

    finally:
        session.close()


def get_user_dependencies(user_id):
    session = get_db_session()

    try:
        user = session.query(User).get(user_id)

        if user is None:
            return None

        projects = (
            session.query(Project)
            .filter(
                Project.owner_user_id == user_id
            )
            .count()
        )

        topologies = (
            session.query(Topology)
            .filter(
                Topology.owner_id == user_id
            )
            .count()
        )

        slices = (
            session.query(Slice)
            .filter(
                Slice.owner_id == user_id
            )
            .count()
        )

        memberships = (
            session.query(ProjectMember)
            .filter(
                ProjectMember.user_id == user_id
            )
            .count()
        )

        return {
            "projects": projects,
            "topologies": topologies,
            "slices": slices,
            "memberships": memberships,
            "can_delete": (
                projects == 0
                and topologies == 0
                and slices == 0
                and memberships == 0
            ),
        }

    finally:
        session.close()


def delete_user(user_id):
    session = get_db_session()

    try:
        record = session.query(User).get(user_id)

        if record is None:
            return False

        projects = (
            session.query(Project)
            .filter(
                Project.owner_user_id == user_id
            )
            .count()
        )

        topologies = (
            session.query(Topology)
            .filter(
                Topology.owner_id == user_id
            )
            .count()
        )

        slices = (
            session.query(Slice)
            .filter(
                Slice.owner_id == user_id
            )
            .count()
        )

        memberships = (
            session.query(ProjectMember)
            .filter(
                ProjectMember.user_id == user_id
            )
            .count()
        )

        blockers = []

        if projects:
            blockers.append(
                "{} proyecto(s)".format(projects)
            )

        if topologies:
            blockers.append(
                "{} topología(s)".format(topologies)
            )

        if slices:
            blockers.append(
                "{} slice(s)".format(slices)
            )

        if memberships:
            blockers.append(
                "{} membresía(s)".format(memberships)
            )

        if blockers:
            raise ValueError(
                "No se puede eliminar al usuario. "
                "Primero debe eliminar o reasignar: {}.".format(
                    ", ".join(blockers)
                )
            )

        session.delete(record)
        session.commit()

        return True

    except Exception:
        session.rollback()
        raise

    finally:
        session.close()
=== FILE: database/repositories/project_repository.py ===
from database.connection import get_db_session
from database.models import (
    Project,
    ProjectMember,
    Slice,
    Topology,
    User,
)


def serialize_project(record):
    return {
        "id": record.id,
        "openstack_project_id":
            record.openstack_project_id,
        "name": record.name,
        "owner_user_id": record.owner_user_id,
        "owner_username": (
            record.owner.username
            if record.owner is not None
            else None
        ),
        "status": record.status,
        "created_at": record.created_at,
    }


def create_project_record(
    openstack_project_id,
    name,
    owner_user_id=None,
    status="ACTIVE",
):
    session = get_db_session()

    try:
        name = str(name).strip()
        status = str(status).strip().upper()

        if not name:
            raise ValueError(
                "El nombre del proyecto es obligatorio."
            )

        if not openstack_project_id:
            raise ValueError(
                "El ID del proyecto OpenStack es obligatorio."
            )

        existing_name = (
            session.query(Project)
            .filter(Project.name == name)
            .first()
        )

        if existing_name is not None:
            raise ValueError(
                "Ya existe un proyecto local llamado '{}'.".format(
                    name
                )
            )

        existing_openstack = (
            session.query(Project)
            .filter(
                Project.openstack_project_id
                == openstack_project_id
            )
            .first()
        )

        if existing_openstack is not None:
            raise ValueError(
                "El proyecto OpenStack ya está registrado."
            )

        if owner_user_id is not None:
            owner = session.query(User).get(
                owner_user_id
            )

            if owner is None:
                raise ValueError(
                    "El propietario no existe."
                )

        record = Project(
            openstack_project_id=openstack_project_id,
            name=name,
            owner_user_id=owner_user_id,
            status=status,
        )

        session.add(record)
        session.commit()
        session.refresh(record)

        return serialize_project(record)

    except Exception:
        session.rollback()
        raise

    finally:
        session.close()


def get_or_create_project(
    openstack_project_id,
    name,
    owner_user_id=None,
):
    session = get_db_session()

    try:
        record = (
            session.query(Project)
            .filter(
                Project.openstack_project_id
                == openstack_project_id
            )
            .first()
        )

        if record is not None:
            return serialize_project(record)

        existing_name = (
            session.query(Project)
            .filter(Project.name == name)
            .first()
        )

        if existing_name is not None:
            existing_name.openstack_project_id = (
                openstack_project_id
            )

            session.commit()
            session.refresh(existing_name)

            return serialize_project(existing_name)

        record = Project(
            openstack_project_id=openstack_project_id,
            name=name,
            owner_user_id=owner_user_id,
            status="ACTIVE",
        )

        session.add(record)
        session.commit()
        session.refresh(record)

        return serialize_project(record)

    except Exception:
        session.rollback()
        raise

    finally:
        session.close()


def get_project_by_id(project_id):
    session = get_db_session()

    try:
        record = session.query(Project).get(
            project_id
        )

        if record is None:
            return None

        return serialize_project(record)

    finally:
        session.close()


def get_project_by_openstack_id(
    openstack_project_id,
):
    session = get_db_session()

    try:
        record = (
            session.query(Project)
            .filter(
                Project.openstack_project_id
                == openstack_project_id
            )
            .first()
        )

        if record is None:
            return None

        return serialize_project(record)

    finally:
        session.close()


def list_projects():
    session = get_db_session()

    try:
        records = (
            session.query(Project)
            .order_by(Project.name.asc())
            .all()
        )

        return [
            serialize_project(record)
            for record in records
        ]

    finally:
        session.close()


def list_projects_for_user(user_id):
    session = get_db_session()

    try:
        records = (
            session.query(Project, ProjectMember)
            .join(
                ProjectMember,
                ProjectMember.project_id == Project.id,
            )
            .filter(
                ProjectMember.user_id == user_id
            )
            .order_by(Project.name.asc())
            .all()
        )

        result = []

        for project, membership in records:
            item = serialize_project(project)

            item["membership_role"] = (
                membership.membership_role
            )

            result.append(item)

        return result

    finally:
        session.close()


def update_project_record(
    project_id,
    name=None,
    status=None,
):
    session = get_db_session()

    try:
        record = session.query(Project).get(
            project_id
        )

        if record is None:
            raise ValueError(
                "El proyecto no existe."
            )

        if name is not None:
            name = name.strip()

            if not name:
                raise ValueError(
                    "El nombre no puede estar vacío."
                )

            duplicated = (
                session.query(Project)
                .filter(
                    Project.name == name,
                    Project.id != project_id,
                )
                .first()
            )

            if duplicated is not None:
                raise ValueError(
                    "Ya existe otro proyecto con ese nombre."
                )

            record.name = name

        if status is not None:
            record.status = status.strip().upper()

        session.commit()
        session.refresh(record)

        return serialize_project(record)

    except Exception:
        session.rollback()
        raise

    finally:
        session.close()


def get_project_dependencies(project_id):
    session = get_db_session()

    try:
        project = session.query(Project).get(
            project_id
        )

        if project is None:
            return None

        memberships = (
            session.query(ProjectMember)
            .filter(
                ProjectMember.project_id == project_id
            )
            .count()
        )

        topologies = (
            session.query(Topology)
            .filter(
                Topology.project_id == project_id
            )
            .count()
        )

        slices = (
            session.query(Slice)
            .filter(
                Slice.project_id == project_id
            )
            .count()
        )

        return {
            "memberships": memberships,
            "topologies": topologies,
            "slices": slices,
            "can_delete": (
                memberships == 0
                and topologies == 0
                and slices == 0
            ),
        }

    finally:
        session.close()


def delete_project_record(project_id):
    session = get_db_session()

    try:
        record = session.query(Project).get(
            project_id
        )

        if record is None:
            return False

        memberships = (
            session.query(ProjectMember)
            .filter(
                ProjectMember.project_id == project_id
            )
            .count()
        )

        topologies = (
            session.query(Topology)
            .filter(
                Topology.project_id == project_id
            )
            .count()
        )

        slices = (
            session.query(Slice)
            .filter(
                Slice.project_id == project_id
            )
            .count()
        )

        if memberships or topologies or slices:
            raise ValueError(
                "No se puede eliminar el proyecto. "
                "Dependencias: {} miembro(s), "
                "{} topología(s), {} slice(s).".format(
                    memberships,
                    topologies,
                    slices,
                )
            )

        session.delete(record)
        session.commit()

        return True

    except Exception:
        session.rollback()
        raise

    finally:
        session.close()
=== FILE: database/repositories/project_member_repository.py ===
from database.connection import get_db_session
from database.models import (
    Project,
    ProjectMember,
    User,
)


VALID_MEMBERSHIP_ROLES = (
    "admin",
    "user",
)


def add_user_to_project(
    project_id,
    user_id,
    membership_role="user",
):
    session = get_db_session()

    try:
        membership_role = membership_role.strip().lower()

        if membership_role not in VALID_MEMBERSHIP_ROLES:
            raise ValueError(
                "Rol de proyecto inválido. Use: admin o user."
            )

        project = session.query(Project).get(project_id)

        if project is None:
            raise ValueError(
                "El proyecto no existe."
            )

        user = session.query(User).get(user_id)

        if user is None:
            raise ValueError(
                "El usuario no existe."
            )

        existing = (
            session.query(ProjectMember)
            .filter(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == user_id,
            )
            .first()
        )

        if existing is not None:
            raise ValueError(
                "El usuario ya está asignado al proyecto."
            )

        record = ProjectMember(
            project_id=project_id,
            user_id=user_id,
            membership_role=membership_role,
        )

        session.add(record)
        session.commit()
        session.refresh(record)

        return {
            "id": record.id,
            "project_id": record.project_id,
            "user_id": record.user_id,
            "membership_role": record.membership_role,
            "created_at": record.created_at,
        }

    except Exception:
        session.rollback()
        raise

    finally:
        session.close()


def get_project_membership(project_id, user_id):
    session = get_db_session()

    try:
        record = (
            session.query(ProjectMember)
            .filter(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == user_id,
            )
            .first()
        )

        if record is None:
            return None

        return {
            "id": record.id,
            "project_id": record.project_id,
            "user_id": record.user_id,
            "membership_role": record.membership_role,
        }

    finally:
        session.close()


def list_project_members(project_id):
    session = get_db_session()

    try:
        records = (
            session.query(ProjectMember, User)
            .join(
                User,
                User.id == ProjectMember.user_id,
            )
            .filter(
                ProjectMember.project_id == project_id
            )
            .order_by(User.username.asc())
            .all()
        )

        return [
            {
                "membership_id": membership.id,
                "project_id": membership.project_id,
                "user_id": user.id,
                "username": user.username,
                "global_role": user.role,
                "membership_role":
                    membership.membership_role,
                "is_active": user.is_active,
            }
            for membership, user in records
        ]

    finally:
        session.close()


def list_user_projects(user_id):
    session = get_db_session()

    try:
        records = (
            session.query(ProjectMember, Project)
            .join(
                Project,
                Project.id == ProjectMember.project_id,
            )
            .filter(
                ProjectMember.user_id == user_id
            )
            .order_by(Project.name.asc())
            .all()
        )

        return [
            {
                "membership_id": membership.id,
                "project_id": project.id,
                "project_name": project.name,
                "openstack_project_id":
                    project.openstack_project_id,
                "project_status": project.status,
                "membership_role":
                    membership.membership_role,
            }
            for membership, project in records
        ]

    finally:
        session.close()


def update_project_membership(
    project_id,
    user_id,
    membership_role,
):
    session = get_db_session()

    try:
        membership_role = membership_role.strip().lower()

        if membership_role not in VALID_MEMBERSHIP_ROLES:
            raise ValueError(
                "Rol de proyecto inválido."
            )

        record = (
            session.query(ProjectMember)
            .filter(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == user_id,
            )
            .first()
        )

        if record is None:
            raise ValueError(
                "El usuario no pertenece al proyecto."
            )

        record.membership_role = membership_role
        session.commit()
        session.refresh(record)

        return {
            "id": record.id,
            "project_id": record.project_id,
            "user_id": record.user_id,
            "membership_role": record.membership_role,
        }

    except Exception:
        session.rollback()
        raise

    finally:
        session.close()


def remove_user_from_project(project_id, user_id):
    session = get_db_session()

    try:
        record = (
            session.query(ProjectMember)
            .filter(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == user_id,
            )
            .first()
        )

        if record is None:
            return False

        session.delete(record)
        session.commit()

        return True

    except Exception:
        session.rollback()
        raise

    finally:
        session.close()
=== FILE: database/repositories/image_repository.py ===
from database.connection import get_db_session
from database.models import ImageResource


VALID_IMAGE_SCOPES = (
    "GLOBAL",
)


def serialize_image(record):
    return {
        "id": record.id,
        "openstack_image_id": record.openstack_image_id,
        "name": record.name,
        "owner_id": record.owner_id,
        "owner_username": (
            record.owner.username
            if record.owner is not None
            else None
        ),
        "project_id": record.project_id,
        "project_name": (
            record.project.name
            if record.project is not None
            else None
        ),
        "scope": record.scope,
        "disk_format": record.disk_format,
        "container_format": record.container_format,
        "status": record.status,
        "size_bytes": record.size_bytes,
        "source_filename": record.source_filename,
        "created_at": record.created_at,
    }


def create_image_record(
    openstack_image_id,
    name,
    owner_id,
    project_id,
    scope="GLOBAL",
    disk_format="qcow2",
    container_format="bare",
    status="ACTIVE",
    size_bytes=None,
    source_filename=None,
):
    session = get_db_session()

    try:
        name = str(name).strip()
        scope = str(scope).strip().upper()
        disk_format = str(disk_format).strip().lower()

        if not name:
            raise ValueError(
                "El nombre de la imagen es obligatorio."
            )

        if scope not in VALID_IMAGE_SCOPES:
            raise ValueError(
                "Alcance inválido. Use USER o PROJECT."
            )

        duplicated_id = (
            session.query(ImageResource)
            .filter(
                ImageResource.openstack_image_id
                == openstack_image_id
            )
            .first()
        )

        if duplicated_id is not None:
            raise ValueError(
                "La imagen de Glance ya está registrada."
            )

        duplicated_name = (
            session.query(ImageResource)
            .filter(
                ImageResource.project_id == project_id,
                ImageResource.name == name,
            )
            .first()
        )

        if duplicated_name is not None:
            raise ValueError(
                "Ya existe una imagen llamada '{}' "
                "dentro del proyecto.".format(name)
            )

        record = ImageResource(
            openstack_image_id=openstack_image_id,
            name=name,
            owner_id=owner_id,
            project_id=project_id,
            scope=scope,
            disk_format=disk_format,
            container_format=container_format,
            status=str(status).upper(),
            size_bytes=size_bytes,
            source_filename=source_filename,
        )

        session.add(record)
        session.commit()
        session.refresh(record)

        return serialize_image(record)

    except Exception:
        session.rollback()
        raise

    finally:
        session.close()


def get_image_by_id(image_id):
    session = get_db_session()

    try:
        record = session.query(ImageResource).get(
            image_id
        )

        if record is None:
            return None

        return serialize_image(record)

    finally:
        session.close()


def get_image_by_openstack_id(openstack_image_id):
    session = get_db_session()

    try:
        record = (
            session.query(ImageResource)
            .filter(
                ImageResource.openstack_image_id
                == openstack_image_id
            )
            .first()
        )

        if record is None:
            return None

        return serialize_image(record)

    finally:
        session.close()

def list_all_images():
    """
    Devuelve el catálogo completo de imágenes.

    No se filtra por usuario ni por proyecto porque
    las imágenes son plantillas globales.
    """

    session = get_db_session()

    try:
        records = (
            session.query(ImageResource)
            .order_by(ImageResource.name.asc())
            .all()
        )

        return [
            serialize_image(record)
            for record in records
        ]

    finally:
        session.close()

def list_visible_images(
    owner_id=None,
    project_id=None,
    role=None,
):
    """
    Compatibilidad con versiones anteriores.

    Todo usuario autenticado puede ver todo el catálogo.
    """

    return list_all_images()


def update_image_status(
    image_id,
    status,
):
    session = get_db_session()

    try:
        record = session.query(ImageResource).get(
            image_id
        )

        if record is None:
            raise ValueError(
                "La imagen no existe."
            )

        record.status = str(status).upper()

        session.commit()
        session.refresh(record)

        return serialize_image(record)

    except Exception:
        session.rollback()
        raise

    finally:
        session.close()


def update_image_scope(
    image_id,
    scope,
):
    session = get_db_session()

    try:
        scope = str(scope).strip().upper()

        if scope not in VALID_IMAGE_SCOPES:
            raise ValueError(
                "Alcance inválido."
            )

        record = session.query(ImageResource).get(
            image_id
        )

        if record is None:
            raise ValueError(
                "La imagen no existe."
            )

        record.scope = scope

        session.commit()
        session.refresh(record)

        return serialize_image(record)

    except Exception:
        session.rollback()
        raise

    finally:
        session.close()


def delete_image_record(image_id):
    session = get_db_session()

    try:
        record = session.query(ImageResource).get(
            image_id
        )

        if record is None:
            return False

        session.delete(record)
        session.commit()

        return True

    except Exception:
        session.rollback()
        raise

    finally:
        session.close()
=== FILE: auth/auth_manager.py ===
import getpass
import os

import openstack

from keystoneauth1 import session
from keystoneauth1.identity import v3

from database.repositories.project_repository import (
    get_or_create_project,
)
from database.repositories.user_repository import (
    get_user_by_keystone_id,
)


class AuthenticationError(Exception):
    pass


def get_auth_url():
    auth_url = os.environ.get("OS_AUTH_URL")

    if not auth_url:
        raise AuthenticationError(
            "No se encontró OS_AUTH_URL. Ejecute primero:\n"
            "source /root/env-scripts/admin-openrc"
        )

    return auth_url.rstrip("/")


def get_user_domain_name():
    return os.environ.get(
        "OS_USER_DOMAIN_NAME",
        "Default",
    )


def create_unscoped_session(username, password):
    """
    Valida usuario y contraseña en Keystone sin seleccionar
    todavía un proyecto.
    """

    auth = v3.Password(
        auth_url=get_auth_url(),
        username=username,
        password=password,
        user_domain_name=get_user_domain_name(),
    )

    keystone_session = session.Session(auth=auth)

    try:
        keystone_session.get_token()

        return {
            "session": keystone_session,
            "keystone_user_id":
                keystone_session.get_user_id(),
        }

    except Exception as error:
        raise AuthenticationError(
            "Credenciales inválidas o error de Keystone: "
            "{}".format(error)
        )


def get_user_projects(unscoped_session):
    """
    Consulta directamente /v3/auth/projects.

    No utiliza openstack.Connection porque un token unscoped
    no contiene catálogo de servicios.
    """

    endpoint = "{}/auth/projects".format(
        get_auth_url()
    )

    try:
        response = unscoped_session.get(
            endpoint,
            authenticated=True,
        )

        response.raise_for_status()

        body = response.json()
        projects = body.get("projects", [])

    except Exception as error:
        raise AuthenticationError(
            "No se pudieron consultar los proyectos "
            "disponibles para el usuario: {}".format(error)
        )

    result = []

    for project in projects:
        if not project.get("enabled", True):
            continue

        result.append({
            "id": project["id"],
            "name": project["name"],
            "domain_id": project.get(
                "domain_id",
                "default",
            ),
            "enabled": project.get(
                "enabled",
                True,
            ),
        })

    return result


def select_project(projects):
    if not projects:
        raise AuthenticationError(
            "El usuario no tiene proyectos asignados."
        )

    print("\n===== SELECCIÓN DE PROYECTO =====")

    for index, project in enumerate(
        projects,
        start=1,
    ):
        print(
            "{}. {}".format(
                index,
                project["name"],
            )
        )

    while True:
        option = input(
            "Seleccione un proyecto: "
        ).strip()

        try:
            selected_index = int(option) - 1

        except ValueError:
            print("Debe ingresar un número.")
            continue

        if (
            selected_index < 0
            or selected_index >= len(projects)
        ):
            print("Proyecto inválido.")
            continue

        return projects[selected_index]


def create_scoped_connection(
    username,
    password,
    project_id,
):
    """
    Crea una nueva sesión limitada al proyecto seleccionado.
    Se usa project_id para evitar ambigüedades de nombre.
    """

    auth = v3.Password(
        auth_url=get_auth_url(),
        username=username,
        password=password,
        user_domain_name=get_user_domain_name(),
        project_id=project_id,
    )

    scoped_session = session.Session(auth=auth)

    try:
        scoped_session.get_token()

        connection = openstack.connection.Connection(
            session=scoped_session,
            region_name=os.environ.get(
                "OS_REGION_NAME",
                "RegionOne",
            ),
        )

        # Obliga a comprobar que el catálogo scoped funciona.
        connection.authorize()

        return {
            "session": scoped_session,
            "connection": connection,
            "project_id":
                scoped_session.get_project_id(),
        }

    except Exception as error:
        raise AuthenticationError(
            "No fue posible iniciar la sesión en el "
            "proyecto seleccionado: {}".format(error)
        )


def authenticate_user(username, password):
    unscoped_data = create_unscoped_session(
        username=username,
        password=password,
    )

    keystone_user_id = unscoped_data[
        "keystone_user_id"
    ]

    local_user = get_user_by_keystone_id(
        keystone_user_id
    )

    if local_user is None:
        raise AuthenticationError(
            "El usuario existe en Keystone, pero no está "
            "registrado en la base del orquestador."
        )

    if not local_user["is_active"]:
        raise AuthenticationError(
            "El usuario está deshabilitado."
        )

    projects = get_user_projects(
        unscoped_session=unscoped_data["session"],
    )

    selected_project = select_project(projects)

    scoped_data = create_scoped_connection(
        username=username,
        password=password,
        project_id=selected_project["id"],
    )

    local_project = get_or_create_project(
        openstack_project_id=scoped_data[
            "project_id"
        ],
        name=selected_project["name"],
        owner_user_id=None,
    )

    return {
        "local_user_id": local_user["id"],
        "keystone_user_id": keystone_user_id,
        "username": local_user["username"],
        "role": local_user["role"].lower(),
        "is_active": local_user["is_active"],

        "local_project_id": local_project["id"],
        "openstack_project_id":
            scoped_data["project_id"],
        "project_name":
            selected_project["name"],

        "connection":
            scoped_data["connection"],
        "keystone_session":
            scoped_data["session"],
    }


def login_interactive():
    print("\n===== INICIO DE SESIÓN =====")

    username = input(
        "Usuario: "
    ).strip()

    if not username:
        print("El usuario es obligatorio.")
        return None

    password = getpass.getpass(
        "Contraseña: "
    )

    try:
        session_context = authenticate_user(
            username=username,
            password=password,
        )

        print("\nInicio de sesión correcto.")
        print(
            "Usuario: {} | Rol: {} | Proyecto: {}".format(
                session_context["username"],
                session_context["role"],
                session_context["project_name"],
            )
        )
        print("\nDEBUG DE SESIÓN")
        print(
            "local_user_id:",
            session_context.get("local_user_id"),
        )
        print(
            "local_project_id:",
            session_context.get("local_project_id"),
        )
        print(
            "openstack_project_id:",
            session_context.get("openstack_project_id"),
        )

        return session_context

    except AuthenticationError as error:
        print("\nError de autenticación:")
        print(error)
        return None
=== FILE: auth/authorization.py ===
class AuthorizationError(Exception):
    pass


def require_authenticated(session_context):
    if session_context is None:
        raise AuthorizationError(
            "Debe iniciar sesión."
        )


def require_role(session_context, *allowed_roles):
    require_authenticated(session_context)

    current_role = session_context.get("role")

    if current_role not in allowed_roles:
        raise AuthorizationError(
            "No tiene permisos para realizar esta operación."
        )


def require_superadmin(session_context):
    require_role(
        session_context,
        "superadmin"
    )


def require_admin_or_superadmin(session_context):
    require_role(
        session_context,
        "superadmin",
        "admin"
    )


def is_superadmin(session_context):
    return (
        session_context is not None
        and session_context.get("role") == "superadmin"
    )


def is_admin(session_context):
    return (
        session_context is not None
        and session_context.get("role") == "admin"
    )


def is_user(session_context):
    return (
        session_context is not None
        and session_context.get("role") == "user"
    )
=== FILE: users/user_manager.py ===
from auth.authorization import (
    AuthorizationError,
    is_admin,
    is_superadmin,
    require_superadmin,
)

from database.repositories.project_member_repository import (
    get_project_membership,
    list_user_projects,
)

from database.repositories.user_repository import (
    create_user,
    delete_user,
    get_user_by_id,
    get_user_dependencies,
    list_all_users,
    list_users_visible_to_admin,
    update_user,
    update_user_status,
)

from projects.project_membership_manager import (
    assign_user_to_project,
    change_project_member_role,
    unassign_user_from_project,
)

from users.keystone_user_service import (
    create_keystone_user,
    delete_keystone_user,
    update_keystone_user,
)


VALID_GLOBAL_ROLES = (
    "superadmin",
    "admin",
    "user",
)

VALID_PROJECT_ROLES = (
    "admin",
    "user",
)


# ============================================================
# VALIDACIONES
# ============================================================

def validate_global_role(role):
    role = str(role).strip().lower()

    if role not in VALID_GLOBAL_ROLES:
        raise ValueError(
            "Rol global inválido. Use: superadmin, admin o user."
        )

    return role


def validate_project_role(membership_role):
    membership_role = str(
        membership_role
    ).strip().lower()

    if membership_role not in VALID_PROJECT_ROLES:
        raise ValueError(
            "Rol de proyecto inválido. Use: admin o user."
        )

    return membership_role


def validate_role_consistency(
    global_role,
    membership_role,
):
    """
    Mantiene una relación simple y consistente:

    - global admin -> project admin
    - global user  -> project user
    - superadmin   -> project admin o user
    """

    global_role = validate_global_role(
        global_role
    )

    membership_role = validate_project_role(
        membership_role
    )

    if (
        global_role == "user"
        and membership_role == "admin"
    ):
        raise ValueError(
            "Un usuario con rol global 'user' no puede ser "
            "administrador de un proyecto."
        )

    if (
        global_role == "admin"
        and membership_role != "admin"
    ):
        raise ValueError(
            "Un usuario con rol global 'admin' debe tener "
            "rol 'admin' dentro del proyecto."
        )

    return True


# ============================================================
# CREAR USUARIO Y ASIGNAR PROYECTO INICIAL
# ============================================================

def create_new_user(
    session_context,
    username,
    password,
    role,
    project_id,
    membership_role,
):
    """
    Crea al usuario en:

    1. Keystone.
    2. SQLite.
    3. Asigna el proyecto en Keystone.
    4. Registra ProjectMember en SQLite.

    La asignación inicial a un proyecto es obligatoria.
    """

    require_superadmin(session_context)

    username = str(username).strip()
    role = validate_global_role(role)
    membership_role = validate_project_role(
        membership_role
    )

    validate_role_consistency(
        global_role=role,
        membership_role=membership_role,
    )

    if not username:
        raise ValueError(
            "El nombre del usuario es obligatorio."
        )

    if not password:
        raise ValueError(
            "La contraseña es obligatoria."
        )

    if project_id is None:
        raise ValueError(
            "Debe asignar un proyecto inicial al usuario."
        )

    keystone_user = None
    local_user = None

    try:
        # 1. Crear usuario en Keystone.
        keystone_user = create_keystone_user(
            username=username,
            password=password,
            enabled=True,
        )

        # 2. Crear usuario en SQLite.
        local_user = create_user(
            username=username,
            keystone_user_id=keystone_user["id"],
            role=role,
        )

        # 3 y 4. Asignar proyecto en Keystone y SQLite.
        membership = assign_user_to_project(
            session_context=session_context,
            user_id=local_user["id"],
            project_id=project_id,
            membership_role=membership_role,
        )

        return {
            "user": local_user,
            "membership": membership,
        }

    except Exception:
        # Rollback local si el usuario alcanzó a crearse.
        if local_user is not None:
            try:
                delete_user(
                    local_user["id"]
                )
            except Exception:
                pass

        # Rollback en Keystone.
        if keystone_user is not None:
            try:
                delete_keystone_user(
                    keystone_user["id"]
                )
            except Exception:
                pass

        raise


# ============================================================
# VISIBILIDAD DE USUARIOS
# ============================================================

def list_visible_users(session_context):
    if is_superadmin(session_context):
        return list_all_users()

    if is_admin(session_context):
        return list_users_visible_to_admin(
            session_context["local_user_id"]
        )

    raise AuthorizationError(
        "Los usuarios con rol 'user' no tienen acceso "
        "al módulo de usuarios."
    )


def get_visible_user(
    session_context,
    user_id,
):
    visible_users = list_visible_users(
        session_context
    )

    visible_ids = [
        user["id"]
        for user in visible_users
    ]

    if user_id not in visible_ids:
        raise AuthorizationError(
            "No tiene permisos para consultar ese usuario."
        )

    return get_user_by_id(user_id)


# ============================================================
# MODIFICAR DATOS DEL USUARIO
# ============================================================

def modify_user(
    session_context,
    user_id,
    username=None,
    password=None,
    role=None,
):
    """
    Modifica únicamente:

    - nombre;
    - contraseña;
    - rol global.

    Las asignaciones de proyectos se administran mediante
    assign_additional_project(), remove_assigned_project()
    y update_assigned_project_role().
    """

    require_superadmin(session_context)

    current_user = get_user_by_id(
        user_id
    )

    if current_user is None:
        raise ValueError(
            "El usuario no existe."
        )

    normalized_role = None

    if role is not None:
        normalized_role = validate_global_role(
            role
        )

    if (
        user_id == session_context["local_user_id"]
        and normalized_role
        and normalized_role != "superadmin"
    ):
        raise ValueError(
            "No puede quitarse su propio rol superadmin."
        )

    # Verifica que el nuevo rol global sea coherente con
    # todas las membresías actuales.
    if normalized_role is not None:
        memberships = list_user_projects(
            user_id
        )

        for membership in memberships:
            validate_role_consistency(
                global_role=normalized_role,
                membership_role=membership[
                    "membership_role"
                ],
            )

    # Actualizar Keystone si cambia username o password.
    if username or password:
        update_keystone_user(
            keystone_user_id=current_user[
                "keystone_user_id"
            ],
            username=username,
            password=password,
        )

    # Actualizar SQLite.
    return update_user(
        user_id=user_id,
        username=username,
        role=normalized_role,
    )


# ============================================================
# ASIGNAR PROYECTOS ADICIONALES
# ============================================================

def assign_additional_project(
    session_context,
    user_id,
    project_id,
    membership_role,
):
    """
    Asigna un proyecto adicional a un usuario existente.
    """

    require_superadmin(session_context)

    current_user = get_user_by_id(
        user_id
    )

    if current_user is None:
        raise ValueError(
            "El usuario no existe."
        )

    membership_role = validate_project_role(
        membership_role
    )

    validate_role_consistency(
        global_role=current_user["role"],
        membership_role=membership_role,
    )

    existing = get_project_membership(
        project_id=project_id,
        user_id=user_id,
    )

    if existing is not None:
        raise ValueError(
            "El usuario ya pertenece a ese proyecto."
        )

    return assign_user_to_project(
        session_context=session_context,
        user_id=user_id,
        project_id=project_id,
        membership_role=membership_role,
    )


# ============================================================
# QUITAR PROYECTO ASIGNADO
# ============================================================

def remove_assigned_project(
    session_context,
    user_id,
    project_id,
):
    """
    Quita la asignación tanto en Keystone como en SQLite.
    """

    require_superadmin(session_context)

    current_user = get_user_by_id(
        user_id
    )

    if current_user is None:
        raise ValueError(
            "El usuario no existe."
        )

    membership = get_project_membership(
        project_id=project_id,
        user_id=user_id,
    )

    if membership is None:
        raise ValueError(
            "El usuario no pertenece a ese proyecto."
        )

    user_projects = list_user_projects(
        user_id
    )

    if len(user_projects) <= 1:
        raise ValueError(
            "No se puede quitar el único proyecto del usuario. "
            "Primero asígnele otro proyecto."
        )

    return unassign_user_from_project(
        session_context=session_context,
        user_id=user_id,
        project_id=project_id,
    )


# ============================================================
# CAMBIAR ROL DENTRO DEL PROYECTO
# ============================================================

def update_assigned_project_role(
    session_context,
    user_id,
    project_id,
    membership_role,
):
    require_superadmin(session_context)

    current_user = get_user_by_id(
        user_id
    )

    if current_user is None:
        raise ValueError(
            "El usuario no existe."
        )

    membership_role = validate_project_role(
        membership_role
    )

    validate_role_consistency(
        global_role=current_user["role"],
        membership_role=membership_role,
    )

    membership = get_project_membership(
        project_id=project_id,
        user_id=user_id,
    )

    if membership is None:
        raise ValueError(
            "El usuario no pertenece a ese proyecto."
        )

    return change_project_member_role(
        session_context=session_context,
        user_id=user_id,
        project_id=project_id,
        membership_role=membership_role,
    )


# ============================================================
# LISTAR PROYECTOS DEL USUARIO
# ============================================================

def get_user_project_assignments(
    session_context,
    user_id,
):
    """
    Superadmin puede consultar cualquier usuario.
    Admin solo puede consultar usuarios visibles.
    """

    if is_superadmin(session_context):
        user = get_user_by_id(
            user_id
        )

        if user is None:
            raise ValueError(
                "El usuario no existe."
            )

    elif is_admin(session_context):
        get_visible_user(
            session_context,
            user_id,
        )

    else:
        raise AuthorizationError(
            "No tiene permisos para consultar "
            "las asignaciones de proyectos."
        )

    return list_user_projects(
        user_id
    )


# ============================================================
# ACTIVAR / DESACTIVAR
# ============================================================

def change_user_status(
    session_context,
    user_id,
    is_active,
):
    require_superadmin(session_context)

    if (
        user_id == session_context["local_user_id"]
        and not is_active
    ):
        raise ValueError(
            "No puede deshabilitar su propio usuario."
        )

    current_user = get_user_by_id(
        user_id
    )

    if current_user is None:
        raise ValueError(
            "El usuario no existe."
        )

    update_keystone_user(
        keystone_user_id=current_user[
            "keystone_user_id"
        ],
        enabled=is_active,
    )

    return update_user_status(
        user_id=user_id,
        is_active=is_active,
    )


# ============================================================
# ELIMINAR USUARIO
# ============================================================

def remove_user(
    session_context,
    user_id,
):
    require_superadmin(session_context)

    if user_id == session_context["local_user_id"]:
        raise ValueError(
            "No puede eliminar su propio usuario."
        )

    current_user = get_user_by_id(
        user_id
    )

    if current_user is None:
        return False

    dependencies = get_user_dependencies(
        user_id
    )

    if not dependencies["can_delete"]:
        raise ValueError(
            "No se puede eliminar. Dependencias: "
            "{} proyecto(s), {} topología(s), {} slice(s), "
            "{} membresía(s). "
            "Primero debe quitar las asignaciones y eliminar "
            "o reasignar sus recursos.".format(
                dependencies["projects"],
                dependencies["topologies"],
                dependencies["slices"],
                dependencies["memberships"],
            )
        )

    # Primero se elimina de Keystone.
    delete_keystone_user(
        current_user["keystone_user_id"]
    )

    # Después se elimina de SQLite.
    return delete_user(
        user_id
    )
=== FILE: users/keystone_user_service.py ===
from common.admin_connection import get_admin_connection


def find_keystone_user(username):
    connection = get_admin_connection()

    return connection.identity.find_user(
        username,
        ignore_missing=True,
    )


def create_keystone_user(
    username,
    password,
    enabled=True,
):
    connection = get_admin_connection()

    existing = connection.identity.find_user(
        username,
        ignore_missing=True,
    )

    if existing is not None:
        raise ValueError(
            "Ya existe un usuario llamado '{}' en Keystone.".format(
                username
            )
        )

    try:
        user = connection.identity.create_user(
            name=username,
            password=password,
            domain_id="default",
            enabled=enabled,
        )

        return {
            "id": user.id,
            "name": user.name,
            "enabled": getattr(
                user,
                "is_enabled",
                True,
            ),
        }

    except Exception as error:
        raise RuntimeError(
            "No se pudo crear el usuario en Keystone: {}".format(
                error
            )
        )


def update_keystone_user(
    keystone_user_id,
    username=None,
    password=None,
    enabled=None,
):
    connection = get_admin_connection()

    user = connection.identity.get_user(
        keystone_user_id
    )

    if user is None:
        raise ValueError(
            "El usuario no existe en Keystone."
        )

    attributes = {}

    if username:
        attributes["name"] = username

    if password:
        attributes["password"] = password

    if enabled is not None:
        attributes["enabled"] = enabled

    if not attributes:
        return {
            "id": user.id,
            "name": user.name,
            "enabled": getattr(
                user,
                "is_enabled",
                True,
            ),
        }

    updated = connection.identity.update_user(
        user,
        **attributes
    )

    return {
        "id": updated.id,
        "name": updated.name,
        "enabled": getattr(
            updated,
            "is_enabled",
            True,
        ),
    }


def delete_keystone_user(keystone_user_id):
    connection = get_admin_connection()

    connection.identity.delete_user(
        keystone_user_id,
        ignore_missing=True,
    )

    return True
=== FILE: projects/project_manager.py ===
from auth.authorization import (
    AuthorizationError,
    is_superadmin,
    require_superadmin,
)

from database.repositories.project_member_repository import (
    list_project_members,
)

from database.repositories.project_repository import (
    create_project_record,
    delete_project_record,
    get_project_by_id,
    get_project_dependencies,
    list_projects,
    list_projects_for_user,
    update_project_record,
)

from projects.keystone_project_service import (
    create_keystone_project,
    delete_keystone_project,
    update_keystone_project,
)


def create_new_project(
    session_context,
    name,
    description=None,
):
    require_superadmin(session_context)

    keystone_project = None

    try:
        keystone_project = create_keystone_project(
            name=name,
            description=description,
        )

        local_project = create_project_record(
            openstack_project_id=keystone_project["id"],
            name=keystone_project["name"],
            owner_user_id=session_context[
                "local_user_id"
            ],
            status="ACTIVE",
        )

        return local_project

    except Exception:
        if keystone_project is not None:
            try:
                delete_keystone_project(
                    keystone_project["id"]
                )
            except Exception:
                pass

        raise


def list_visible_projects(session_context):
    if is_superadmin(session_context):
        return list_projects()

    return list_projects_for_user(
        session_context["local_user_id"]
    )


def get_visible_project(
    session_context,
    project_id,
):
    project = get_project_by_id(
        project_id
    )

    if project is None:
        return None

    if is_superadmin(session_context):
        return project

    visible_projects = list_projects_for_user(
        session_context["local_user_id"]
    )

    visible_ids = [
        item["id"]
        for item in visible_projects
    ]

    if project_id not in visible_ids:
        raise AuthorizationError(
            "No tiene permisos para consultar ese proyecto."
        )

    return project


def modify_project(
    session_context,
    project_id,
    name=None,
    description=None,
    status=None,
):
    require_superadmin(session_context)

    project = get_project_by_id(
        project_id
    )

    if project is None:
        raise ValueError(
            "El proyecto no existe."
        )

    enabled = None

    if status is not None:
        normalized_status = status.strip().upper()

        if normalized_status not in (
            "ACTIVE",
            "DISABLED",
        ):
            raise ValueError(
                "Estado inválido."
            )

        enabled = (
            normalized_status == "ACTIVE"
        )

    update_keystone_project(
        openstack_project_id=project[
            "openstack_project_id"
        ],
        name=name,
        description=description,
        enabled=enabled,
    )

    return update_project_record(
        project_id=project_id,
        name=name,
        status=status,
    )


def remove_project(
    session_context,
    project_id,
):
    require_superadmin(session_context)

    project = get_project_by_id(
        project_id
    )

    if project is None:
        return False

    dependencies = get_project_dependencies(
        project_id
    )

    if not dependencies["can_delete"]:
        raise ValueError(
            "No se puede eliminar. Dependencias: "
            "{} miembro(s), {} topología(s), "
            "{} slice(s).".format(
                dependencies["memberships"],
                dependencies["topologies"],
                dependencies["slices"],
            )
        )

    delete_keystone_project(
        project["openstack_project_id"]
    )

    return delete_project_record(
        project_id
    )


def get_project_detail(
    session_context,
    project_id,
):
    project = get_visible_project(
        session_context=session_context,
        project_id=project_id,
    )

    if project is None:
        return None

    members = list_project_members(
        project_id
    )

    project["members"] = members

    return project
=== FILE: projects/keystone_project_service.py ===
from common.admin_connection import get_admin_connection


def create_keystone_project(
    name,
    description=None,
):
    connection = get_admin_connection()

    name = str(name).strip()

    if not name:
        raise ValueError(
            "El nombre del proyecto es obligatorio."
        )

    existing = connection.identity.find_project(
        name,
        ignore_missing=True,
    )

    if existing is not None:
        raise ValueError(
            "Ya existe un proyecto llamado '{}' en Keystone.".format(
                name
            )
        )

    try:
        project = connection.identity.create_project(
            name=name,
            description=description or "",
            domain_id="default",
            enabled=True,
        )

        return {
            "id": project.id,
            "name": project.name,
            "description": getattr(
                project,
                "description",
                "",
            ),
            "enabled": getattr(
                project,
                "is_enabled",
                True,
            ),
        }

    except Exception as error:
        raise RuntimeError(
            "No se pudo crear el proyecto en Keystone: {}".format(
                error
            )
        )


def update_keystone_project(
    openstack_project_id,
    name=None,
    description=None,
    enabled=None,
):
    connection = get_admin_connection()

    project = connection.identity.get_project(
        openstack_project_id
    )

    if project is None:
        raise ValueError(
            "El proyecto no existe en Keystone."
        )

    attributes = {}

    if name is not None:
        name = name.strip()

        if not name:
            raise ValueError(
                "El nombre no puede estar vacío."
            )

        attributes["name"] = name

    if description is not None:
        attributes["description"] = description

    if enabled is not None:
        attributes["enabled"] = bool(enabled)

    if not attributes:
        return {
            "id": project.id,
            "name": project.name,
            "description": getattr(
                project,
                "description",
                "",
            ),
            "enabled": getattr(
                project,
                "is_enabled",
                True,
            ),
        }

    updated = connection.identity.update_project(
        project,
        **attributes
    )

    return {
        "id": updated.id,
        "name": updated.name,
        "description": getattr(
            updated,
            "description",
            "",
        ),
        "enabled": getattr(
            updated,
            "is_enabled",
            True,
        ),
    }

def _find_member_role(connection):
    role = connection.identity.find_role(
        "member",
        ignore_missing=True,
    )

    if role is None:
        role = connection.identity.find_role(
            "_member_",
            ignore_missing=True,
        )

    if role is None:
        raise RuntimeError(
            "No se encontró el rol 'member' ni '_member_' "
            "en Keystone."
        )

    return role

def _has_project_role(
    connection,
    keystone_user_id,
    openstack_project_id,
    role_id,
):
    """
    Comprueba si el usuario ya tiene el rol dentro del proyecto.

    Esta versión usa los nombres de filtros compatibles con
    versiones antiguas de openstacksdk.
    """

    assignments = list(
        connection.identity.role_assignments(
            user_id=keystone_user_id,
            scope_project_id=openstack_project_id,
            role_id=role_id,
        )
    )

    return len(assignments) > 0


def assign_user_to_keystone_project(
    keystone_user_id,
    openstack_project_id,
):
    connection = get_admin_connection()

    user = connection.identity.get_user(
        keystone_user_id
    )

    if user is None:
        raise ValueError(
            "El usuario no existe en Keystone."
        )

    project = connection.identity.get_project(
        openstack_project_id
    )

    if project is None:
        raise ValueError(
            "El proyecto no existe en Keystone."
        )

    role = _find_member_role(connection)

    if _has_project_role(
        connection=connection,
        keystone_user_id=user.id,
        openstack_project_id=project.id,
        role_id=role.id,
    ):
        return True

    try:
        connection.identity.assign_project_role_to_user(
            project=project,
            user=user,
            role=role,
        )

        return True

    except Exception as error:
        raise RuntimeError(
            "No se pudo asignar el usuario al proyecto "
            "en Keystone: {}".format(error)
        )



def remove_user_from_keystone_project(
    keystone_user_id,
    openstack_project_id,
):
    connection = get_admin_connection()

    user = connection.identity.get_user(
        keystone_user_id
    )

    if user is None:
        return False

    project = connection.identity.get_project(
        openstack_project_id
    )

    if project is None:
        return False

    role = _find_member_role(connection)

    if not _has_project_role(
        connection=connection,
        keystone_user_id=user.id,
        openstack_project_id=project.id,
        role_id=role.id,
    ):
        return True

    try:
        connection.identity.unassign_project_role_from_user(
            project=project,
            user=user,
            role=role,
        )

        return True

    except Exception as error:
        raise RuntimeError(
            "No se pudo quitar al usuario del proyecto "
            "en Keystone: {}".format(error)
        )

def delete_keystone_project(
    openstack_project_id,
    ):
    connection = get_admin_connection()

    connection.identity.delete_project(
        openstack_project_id,
        ignore_missing=True,
    )

    return True
=== FILE: images/image_manager.py ===
import os

from common.admin_connection import get_admin_connection

from database.repositories.image_repository import (
    create_image_record,
    delete_image_record,
    get_image_by_id,
    list_all_images,
)

from images.glance_image_service import (
    delete_glance_image,
    detect_disk_format,
    get_glance_image,
    upload_image_to_glance,
)

def get_image_context(session_context):
    if session_context is None:
        raise ValueError(
            "No existe una sesión autenticada."
        )

    owner_id = session_context.get(
        "local_user_id"
    )

    project_id = session_context.get(
        "local_project_id"
    )

    role = str(
        session_context.get(
            "role",
            "",
        )
    ).strip().lower()

    if owner_id is None:
        raise ValueError(
            "La sesión no contiene local_user_id."
        )

    if project_id is None:
        raise ValueError(
            "La sesión no contiene local_project_id."
        )

    if role not in (
        "superadmin",
        "admin",
        "user",
    ):
        raise ValueError(
            "El rol de la sesión no es válido."
        )

    return {
        "owner_id": owner_id,
        "project_id": project_id,
        "role": role,
    }

def require_image_admin(session_context):
    context = get_image_context(
        session_context
    )

    if context["role"] not in (
        "superadmin",
        "admin",
    ):
        raise PermissionError(
            "Solo los administradores pueden subir "
            "o eliminar imágenes."
        )

    return context

def upload_new_image(
    session_context,
    name,
    file_path,
    disk_format=None,
):
    context = require_image_admin(
        session_context
    )

    name = str(name).strip()

    if not name:
        raise ValueError(
            "El nombre de la imagen es obligatorio."
        )

    file_path = os.path.abspath(
        os.path.expanduser(
            str(file_path).strip()
        )
    )

    if not os.path.isfile(file_path):
        raise ValueError(
            "El archivo no existe: {}".format(
                file_path
            )
        )

    if disk_format is None:
        disk_format = detect_disk_format(
            file_path
        )

    disk_format = str(
        disk_format
    ).strip().lower()

    # La imagen se publica globalmente, por eso se usa
    # una conexión administrativa y visibility="public".
    admin_connection = get_admin_connection()

    glance_image = None

    try:
        glance_image = upload_image_to_glance(
            connection=admin_connection,
            name=name,
            file_path=file_path,
            disk_format=disk_format,
            visibility="public",
        )

        glance_status = str(
            getattr(
                glance_image,
                "status",
                "ACTIVE",
            )
        ).upper()

        size_bytes = getattr(
            glance_image,
            "size",
            None,
        )

        if size_bytes is None:
            size_bytes = os.path.getsize(
                file_path
            )

        return create_image_record(
            openstack_image_id=glance_image.id,
            name=name,
            owner_id=context["owner_id"],

            # Se conserva por compatibilidad con tu modelo actual.
            # Ya no se usa para restringir la visibilidad.
            project_id=context["project_id"],

            scope="GLOBAL",
            disk_format=disk_format,
            container_format="bare",
            status=glance_status,
            size_bytes=size_bytes,
            source_filename=os.path.basename(
                file_path
            ),
        )

    except Exception:
        if glance_image is not None:
            try:
                delete_glance_image(
                    connection=admin_connection,
                    openstack_image_id=glance_image.id,
                )
            except Exception:
                pass

        raise

def get_catalog_images(session_context):
    get_image_context(
        session_context
    )

    records = list_all_images()

    try:
        admin_connection = get_admin_connection()
    except Exception:
        admin_connection = None

    result = []

    for record in records:
        item = dict(record)

        if admin_connection is None:
            item["glance_status"] = item.get(
                "status",
                "UNKNOWN",
            )

            result.append(item)
            continue

        try:
            glance_image = get_glance_image(
                connection=admin_connection,
                openstack_image_id=item[
                    "openstack_image_id"
                ],
            )

            if glance_image is None:
                item["glance_status"] = "NOT_FOUND"
            else:
                item["glance_status"] = str(
                    getattr(
                        glance_image,
                        "status",
                        item.get(
                            "status",
                            "UNKNOWN",
                        ),
                    )
                ).upper()

        except Exception:
            item["glance_status"] = "UNAVAILABLE"

        result.append(item)

    return result

def get_visible_images(session_context):
    return get_catalog_images(
        session_context
    )

def delete_image(
    session_context,
    image_id,
):
    require_image_admin(
        session_context
    )

    record = get_image_by_id(
        image_id
    )

    if record is None:
        return False

    admin_connection = get_admin_connection()

    delete_glance_image(
        connection=admin_connection,
        openstack_image_id=record[
            "openstack_image_id"
        ],
    )

    return delete_image_record(
        image_id
    )
=== FILE: images/glance_image_service.py ===
import os


VALID_DISK_FORMATS = (
    "qcow2",
    "raw",
    "vmdk",
)


def detect_disk_format(file_path):
    extension = os.path.splitext(
        file_path
    )[1].lower().lstrip(".")

    format_map = {
        "qcow2": "qcow2",
        "img": "qcow2",
        "raw": "raw",
        "vmdk": "vmdk",
    }

    if extension not in format_map:
        raise ValueError(
            "No se pudo detectar el formato. "
            "Use archivos qcow2, img, raw o vmdk."
        )

    return format_map[extension]


def upload_image_to_glance(
    connection,
    name,
    file_path,
    disk_format,
    visibility="public",
    timeout=3600,
):
    if connection is None:
        raise ValueError(
            "No existe una conexión OpenStack."
        )

    name = str(name).strip()

    if not name:
        raise ValueError(
            "El nombre de la imagen es obligatorio."
        )

    file_path = os.path.abspath(
        os.path.expanduser(
            str(file_path).strip()
        )
    )

    if not os.path.isfile(file_path):
        raise ValueError(
            "El archivo no existe: {}".format(
                file_path
            )
        )

    disk_format = str(
        disk_format
    ).strip().lower()

    if disk_format not in VALID_DISK_FORMATS:
        raise ValueError(
            "Formato inválido. Use qcow2, raw o vmdk."
        )

    try:
        image = connection.create_image(
            name=name,
            filename=file_path,
            disk_format=disk_format,
            container_format="bare",
            visibility=visibility,
            wait=True,
            timeout=timeout,
            allow_duplicates=False,
        )

        if image is None:
            raise RuntimeError(
                "OpenStack no devolvió la imagen creada."
            )

        image_id = getattr(
            image,
            "id",
            None,
        )

        if not image_id:
            raise RuntimeError(
                "La imagen fue creada sin un ID válido."
            )

        refreshed_image = connection.image.get_image(
            image_id
        )

        if refreshed_image is None:
            raise RuntimeError(
                "La imagen no pudo consultarse después "
                "de la carga."
            )

        status = str(
            getattr(
                refreshed_image,
                "status",
                "",
            )
        ).lower()

        if status != "active":
            raise RuntimeError(
                "La imagen quedó en estado '{}'.".format(
                    status or "desconocido"
                )
            )

        return refreshed_image

    except Exception as error:
        raise RuntimeError(
            "No se pudo crear y cargar la imagen "
            "en Glance: {}".format(error)
        )


def get_glance_image(
    connection,
    openstack_image_id,
):
    return connection.image.get_image(
        openstack_image_id
    )


def delete_glance_image(
    connection,
    openstack_image_id,
):
    connection.image.delete_image(
        openstack_image_id,
        ignore_missing=True,
    )

    return True
=== FILE: placement/placement_engine.py ===
import copy


class PlacementError(Exception):
    pass


def normalize_vm_requirements(vm):
    """
    Obtiene los requerimientos desde el flavor almacenado
    en la definición de la topología.
    """

    if not isinstance(vm, dict):
        raise PlacementError(
            "La definición de una VM tiene formato inválido."
        )

    vm_name = str(
        vm.get("name", "")
    ).strip()

    if not vm_name:
        raise PlacementError(
            "Existe una VM sin nombre."
        )

    flavor = vm.get(
        "flavor",
        {}
    )

    try:
        required_vcpus = int(
            flavor.get(
                "vcpus",
                0,
            )
        )

        required_ram_mb = int(
            flavor.get(
                "ram",
                0,
            )
        )

        required_disk_gb = int(
            flavor.get(
                "disk",
                0,
            )
        )

    except (TypeError, ValueError):
        raise PlacementError(
            "El flavor de '{}' tiene recursos inválidos.".format(
                vm_name
            )
        )

    if required_vcpus <= 0:
        raise PlacementError(
            "La VM '{}' no tiene un valor válido de vCPU.".format(
                vm_name
            )
        )

    if required_ram_mb <= 0:
        raise PlacementError(
            "La VM '{}' no tiene un valor válido de RAM.".format(
                vm_name
            )
        )

    # Algunos flavors pueden tener disk=0 y usar un volumen
    # o el tamaño mínimo de la imagen.
    if required_disk_gb < 0:
        raise PlacementError(
            "La VM '{}' tiene un disco inválido.".format(
                vm_name
            )
        )

    return {
        "vm_name": vm_name,

        "image_id": (
            vm.get("image", {})
            .get("id")
        ),

        "image_name": (
            vm.get("image", {})
            .get("name")
        ),

        "flavor_id": flavor.get(
            "id"
        ),

        "flavor_name": flavor.get(
            "name"
        ),

        "required_vcpus": required_vcpus,
        "required_ram_mb": required_ram_mb,
        "required_disk_gb": required_disk_gb,
    }


def worker_can_host_vm(
    worker,
    requirements,
):
    if not worker.get(
        "is_available",
        False,
    ):
        return False

    return (
        worker["free_vcpus"]
        >= requirements["required_vcpus"]
        and worker["free_ram_mb"]
        >= requirements["required_ram_mb"]
        and worker["free_disk_gb"]
        >= requirements["required_disk_gb"]
    )


def create_first_fit_plan(
    vms,
    workers,
):
    """
    First Fit:

    1. Recorre las VMs en el orden de la topología.
    2. Recorre los workers en orden.
    3. Selecciona el primer worker con capacidad.
    4. Resta virtualmente los recursos reservados.
    """

    if not vms:
        raise PlacementError(
            "La topología no contiene máquinas virtuales."
        )

    available_workers = [
        worker
        for worker in workers
        if worker.get("is_available")
    ]

    if not available_workers:
        raise PlacementError(
            "No existen workers disponibles."
        )

    # Copia independiente para realizar reservas virtuales.
    simulated_workers = copy.deepcopy(
        available_workers
    )

    assignments = []
    unplaced_vms = []

    for vm in vms:
        requirements = normalize_vm_requirements(
            vm
        )

        selected_worker = None

        for worker in simulated_workers:
            if worker_can_host_vm(
                worker,
                requirements,
            ):
                selected_worker = worker
                break

        if selected_worker is None:
            unplaced_vms.append({
                "vm_name": requirements[
                    "vm_name"
                ],
                "required_vcpus": requirements[
                    "required_vcpus"
                ],
                "required_ram_mb": requirements[
                    "required_ram_mb"
                ],
                "required_disk_gb": requirements[
                    "required_disk_gb"
                ],
                "reason": (
                    "No existe un worker con recursos suficientes."
                ),
            })

            continue

        resources_before = {
            "free_vcpus":
                selected_worker["free_vcpus"],

            "free_ram_mb":
                selected_worker["free_ram_mb"],

            "free_disk_gb":
                selected_worker["free_disk_gb"],
        }

        # Reserva virtual.
        selected_worker["free_vcpus"] -= (
            requirements["required_vcpus"]
        )

        selected_worker["free_ram_mb"] -= (
            requirements["required_ram_mb"]
        )

        selected_worker["free_disk_gb"] -= (
            requirements["required_disk_gb"]
        )

        resources_after = {
            "free_vcpus":
                selected_worker["free_vcpus"],

            "free_ram_mb":
                selected_worker["free_ram_mb"],

            "free_disk_gb":
                selected_worker["free_disk_gb"],
        }

        assignments.append({
            "vm_name": requirements["vm_name"],

            "image_id": requirements["image_id"],
            "image_name": requirements["image_name"],

            "flavor_id": requirements["flavor_id"],
            "flavor_name": requirements["flavor_name"],

            "required_vcpus":
                requirements["required_vcpus"],

            "required_ram_mb":
                requirements["required_ram_mb"],

            "required_disk_gb":
                requirements["required_disk_gb"],

            "worker": selected_worker["worker"],

            "hypervisor_hostname":
                selected_worker[
                    "hypervisor_hostname"
                ],

            "availability_zone":
                selected_worker[
                    "availability_zone"
                ],

            "resources_before": resources_before,
            "resources_after": resources_after,
        })

    success = len(unplaced_vms) == 0

    return {
        "algorithm": "FIRST_FIT",
        "success": success,
        "assignments": assignments,
        "unplaced_vms": unplaced_vms,
        "workers_after_reservation":
            simulated_workers,
    }
=== FILE: placement/placement_manager.py ===
import json
import os
from datetime import datetime
from common.admin_connection import get_admin_connection

from database.repositories.topology_repository import (
    get_topology,
    list_topologies,
)

from placement.placement_engine import (
    PlacementError,
    create_first_fit_plan,
)

from placement.providers.nova_provider import (
    get_hypervisor_resources,
)


PLACEMENT_PLAN_DIRECTORY = "placement_plans"

os.makedirs(
    PLACEMENT_PLAN_DIRECTORY,
    exist_ok=True,
)


def get_placement_context(session_context):
    if session_context is None:
        raise ValueError(
            "No existe una sesión autenticada."
        )

    owner_id = session_context.get(
        "local_user_id"
    )

    project_id = session_context.get(
        "local_project_id"
    )

    role = str(
        session_context.get(
            "role",
            "",
        )
    ).lower()

    connection = session_context.get(
        "connection"
    )

    if owner_id is None:
        raise ValueError(
            "La sesión no contiene local_user_id."
        )

    if project_id is None:
        raise ValueError(
            "La sesión no contiene local_project_id."
        )

    if not role:
        raise ValueError(
            "La sesión no contiene el rol."
        )

    if connection is None:
        raise ValueError(
            "La sesión no contiene conexión OpenStack."
        )

    return {
        "owner_id": owner_id,
        "project_id": project_id,
        "role": role,
        "connection": connection,
    }


def list_ready_topologies(
    session_context,
):
    context = get_placement_context(
        session_context
    )

    records = list_topologies(
        owner_id=context["owner_id"],
        project_id=context["project_id"],
        role=context["role"],
    )

    return [
        record
        for record in records
        if str(
            record.get("status", "")
        ).upper() == "READY"
    ]


def show_worker_resources(
    session_context,
):
    context = get_placement_context(
        session_context
    )

    # Opcional: solamente administradores pueden visualizar
    # detalles de capacidad de los workers.
    if context["role"] not in (
        "superadmin",
        "admin",
    ):
        raise PermissionError(
            "Solo los administradores pueden consultar "
            "el detalle de los workers."
        )

    placement_connection = get_admin_connection()

    workers = get_hypervisor_resources(
        placement_connection
    )

    if not workers:
        print(
            "\nNova no reportó hipervisores."
        )
        return []

    print("\n===== RECURSOS DE WORKERS =====")

    for worker in workers:
        print(
            "{} | Estado: {} | vCPU libre: {}/{} | "
            "RAM libre: {} MB | Disco libre: {} GB | "
            "VMs: {}".format(
                worker["worker"],
                (
                    "DISPONIBLE"
                    if worker["is_available"]
                    else "NO DISPONIBLE"
                ),
                worker["free_vcpus"],
                worker["total_vcpus"],
                worker["free_ram_mb"],
                worker["free_disk_gb"],
                worker["running_vms"],
            )
        )

    return workers


def generate_placement_plan(
    session_context,
    topology_id,
):
    context = get_placement_context(
        session_context
    )

    # La topología se consulta respetando la identidad y
    # visibilidad del usuario autenticado.
    topology = get_topology(
        topology_id=topology_id,
        owner_id=context["owner_id"],
        project_id=context["project_id"],
        role=context["role"],
    )

    if topology is None:
        raise ValueError(
            "La topología no existe o no tiene permisos."
        )

    if str(
        topology["status"]
    ).upper() != "READY":
        raise ValueError(
            "Solo se puede generar Placement para "
            "topologías en estado READY."
        )

    topology_data = topology[
        "topology_data"
    ]

    vms = topology_data.get(
        "vms",
        []
    )

    # Consultar hipervisores requiere una conexión interna
    # con permisos administrativos. No se utiliza la
    # conexión del usuario para esta operación.
    try:
        placement_connection = get_admin_connection()

    except Exception as error:
        raise RuntimeError(
            "No se pudo crear la conexión administrativa "
            "para VM Placement: {}".format(error)
        )

    workers = get_hypervisor_resources(
        placement_connection
    )

    plan = create_first_fit_plan(
        vms=vms,
        workers=workers,
    )

    plan["topology_id"] = topology["id"]
    plan["topology_name"] = topology["name"]
    plan["project_id"] = context["project_id"]

    plan["project_name"] = (
        session_context.get(
            "project_name"
        )
    )

    plan["generated_by_user_id"] = context[
        "owner_id"
    ]

    plan["generated_at"] = (
        datetime.utcnow().isoformat()
    )

    return plan


def save_placement_plan(plan):
    topology_name = str(
        plan["topology_name"]
    )

    safe_name = "".join(
        character
        if character.isalnum()
        or character in ("-", "_")
        else "_"
        for character in topology_name
    )

    path = os.path.join(
        PLACEMENT_PLAN_DIRECTORY,
        "{}_placement.json".format(
            safe_name
        ),
    )

    with open(
        path,
        "w",
        encoding="utf-8",
    ) as output_file:
        json.dump(
            plan,
            output_file,
            indent=4,
            ensure_ascii=False,
        )

    return path


def show_placement_plan(plan):
    print("\n===== PLAN DE VM PLACEMENT =====")
    print("Topología:", plan["topology_name"])
    print("Algoritmo:", plan["algorithm"])
    print(
        "Resultado:",
        "COMPLETO"
        if plan["success"]
        else "INCOMPLETO",
    )

    print("\nAsignaciones:")

    if not plan["assignments"]:
        print("- No se asignó ninguna VM.")

    for assignment in plan["assignments"]:
        print(
            "- {} → {} | AZ: {} | "
            "{} vCPU | {} MB RAM | {} GB disco".format(
                assignment["vm_name"],
                assignment["worker"],
                assignment["availability_zone"],
                assignment["required_vcpus"],
                assignment["required_ram_mb"],
                assignment["required_disk_gb"],
            )
        )

    if plan["unplaced_vms"]:
        print("\nVMs sin ubicación:")

        for vm in plan["unplaced_vms"]:
            print(
                "- {} | Requiere: {} vCPU, {} MB RAM, "
                "{} GB disco | Motivo: {}".format(
                    vm["vm_name"],
                    vm["required_vcpus"],
                    vm["required_ram_mb"],
                    vm["required_disk_gb"],
                    vm["reason"],
                )
            )
=== FILE: placement/providers/nova_provider.py ===
def _get_value(resource, *keys, default=None):
    """
    Busca un valor tanto como atributo del recurso
    como dentro de resource.to_dict().
    """

    data = {}

    try:
        data = resource.to_dict()
    except Exception:
        pass

    for key in keys:
        value = getattr(
            resource,
            key,
            None,
        )

        if value is not None:
            return value

        if key in data and data[key] is not None:
            return data[key]

    return default


def _normalize_host(hostname):
    if not hostname:
        return None

    return str(hostname).split(".")[0]


def get_compute_services(connection):
    """
    Consulta los servicios nova-compute para determinar
    si cada worker está activo y habilitado.
    """

    services = {}

    try:
        compute_services = connection.compute.services(
            binary="nova-compute"
        )

        for service in compute_services:
            host = _get_value(
                service,
                "host",
                default=None,
            )

            if not host:
                continue

            normalized_host = _normalize_host(
                host
            )

            state = str(
                _get_value(
                    service,
                    "state",
                    default="unknown",
                )
            ).lower()

            status = str(
                _get_value(
                    service,
                    "status",
                    default="enabled",
                )
            ).lower()

            services[normalized_host] = {
                "state": state,
                "status": status,
                "is_up": (
                    state == "up"
                    and status == "enabled"
                ),
            }

    except Exception:
        # Si la versión del SDK no permite consultar
        # servicios, se usará el estado del hipervisor.
        return {}

    return services


def get_hypervisor_resources(connection):
    """
    Obtiene capacidad de CPU, RAM y disco de los
    hipervisores reportados por Nova.
    """

    if connection is None:
        raise ValueError(
            "No existe una conexión OpenStack."
        )

    compute_services = get_compute_services(
        connection
    )

    workers = []

    try:
        hypervisors = connection.compute.hypervisors(
            details=True
        )

        for hypervisor in hypervisors:
            hostname = _get_value(
                hypervisor,
                "name",
                "hypervisor_hostname",
                default=None,
            )

            if not hostname:
                continue

            hostname = str(hostname)

            normalized_host = _normalize_host(
                hostname
            )

            total_vcpus = int(
                _get_value(
                    hypervisor,
                    "vcpus",
                    default=0,
                ) or 0
            )

            used_vcpus = int(
                _get_value(
                    hypervisor,
                    "vcpus_used",
                    default=0,
                ) or 0
            )

            total_ram_mb = int(
                _get_value(
                    hypervisor,
                    "memory_size",
                    "memory_mb",
                    default=0,
                ) or 0
            )

            free_ram_mb = _get_value(
                hypervisor,
                "memory_free",
                "free_ram_mb",
                default=None,
            )

            if free_ram_mb is None:
                used_ram_mb = int(
                    _get_value(
                        hypervisor,
                        "memory_used",
                        "memory_mb_used",
                        default=0,
                    ) or 0
                )

                free_ram_mb = max(
                    total_ram_mb - used_ram_mb,
                    0,
                )
            else:
                free_ram_mb = int(
                    free_ram_mb
                )

            total_disk_gb = int(
                _get_value(
                    hypervisor,
                    "local_disk_size",
                    "local_gb",
                    default=0,
                ) or 0
            )

            free_disk_gb = _get_value(
                hypervisor,
                "local_disk_free",
                "free_disk_gb",
                "free_disk",
                default=None,
            )

            if free_disk_gb is None:
                used_disk_gb = int(
                    _get_value(
                        hypervisor,
                        "local_disk_used",
                        "local_gb_used",
                        default=0,
                    ) or 0
                )

                free_disk_gb = max(
                    total_disk_gb - used_disk_gb,
                    0,
                )
            else:
                free_disk_gb = int(
                    free_disk_gb
                )

            running_vms = int(
                _get_value(
                    hypervisor,
                    "running_vms",
                    default=0,
                ) or 0
            )

            hypervisor_state = str(
                _get_value(
                    hypervisor,
                    "state",
                    default="up",
                )
            ).lower()

            hypervisor_status = str(
                _get_value(
                    hypervisor,
                    "status",
                    default="enabled",
                )
            ).lower()

            service_data = compute_services.get(
                normalized_host
            )

            if service_data is not None:
                is_available = service_data[
                    "is_up"
                ]

                service_state = service_data[
                    "state"
                ]

                service_status = service_data[
                    "status"
                ]

            else:
                is_available = (
                    hypervisor_state == "up"
                    and hypervisor_status == "enabled"
                )

                service_state = hypervisor_state
                service_status = hypervisor_status

            workers.append({
                "worker": normalized_host,
                "hypervisor_hostname": hostname,

                "availability_zone":
                    "nova:{}".format(hostname),

                "total_vcpus": total_vcpus,
                "used_vcpus": used_vcpus,
                "free_vcpus": max(
                    total_vcpus - used_vcpus,
                    0,
                ),

                "total_ram_mb": total_ram_mb,
                "free_ram_mb": free_ram_mb,

                "total_disk_gb": total_disk_gb,
                "free_disk_gb": free_disk_gb,

                "running_vms": running_vms,

                "service_state": service_state,
                "service_status": service_status,
                "is_available": is_available,
            })

    except Exception as error:
        raise RuntimeError(
            "No se pudieron consultar los hipervisores "
            "de Nova: {}".format(error)
        )

    workers.sort(
        key=lambda worker: worker["worker"]
    )

    return workers
=== FILE: deployment/network_deployer.py ===
import ipaddress

from database.repositories.network_resource_repository import (
    create_network_resource_record,
    create_slice_link_record,
    delete_network_resource_record,
    update_network_resource_openstack,
)


DEFAULT_ADDRESS_POOL = "10.200.0.0/16"
DEFAULT_PREFIX_LENGTH = 29


class NetworkDeploymentError(Exception):
    pass


def normalize_vm_name(vm):
    if isinstance(vm, str):
        return vm.strip()

    if isinstance(vm, dict):
        return str(
            vm.get("name", "")
        ).strip()

    return ""


def canonical_link_key(
    source_vm,
    target_vm,
):
    names = sorted([
        str(source_vm).strip(),
        str(target_vm).strip(),
    ])

    return "{}--{}".format(
        names[0],
        names[1],
    )


def build_network_segments(
    topology_data,
):
    """
    Cada enlace lógico se transforma en una red Neutron.

    Una VM sin enlaces recibe una red individual aislada
    para disponer de una interfaz e IP.
    """

    if not isinstance(topology_data, dict):
        raise NetworkDeploymentError(
            "La topología tiene formato inválido."
        )

    vms = topology_data.get(
        "vms",
        []
    )

    links = topology_data.get(
        "links",
        []
    )

    vm_names = []

    for vm in vms:
        vm_name = normalize_vm_name(
            vm
        )

        if not vm_name:
            raise NetworkDeploymentError(
                "Existe una VM sin nombre."
            )

        if vm_name in vm_names:
            raise NetworkDeploymentError(
                "Nombre de VM duplicado: {}.".format(
                    vm_name
                )
            )

        vm_names.append(
            vm_name
        )

    if not vm_names:
        raise NetworkDeploymentError(
            "La topología no contiene VMs."
        )

    known_vms = set(vm_names)
    connected_vms = set()
    known_link_keys = set()
    segments = []

    for link in links:
        if not isinstance(link, dict):
            raise NetworkDeploymentError(
                "Existe un enlace con formato inválido."
            )

        source_vm = str(
            link.get("source", "")
        ).strip()

        target_vm = str(
            link.get("target", "")
        ).strip()

        if source_vm not in known_vms:
            raise NetworkDeploymentError(
                "La VM origen '{}' no existe.".format(
                    source_vm
                )
            )

        if target_vm not in known_vms:
            raise NetworkDeploymentError(
                "La VM destino '{}' no existe.".format(
                    target_vm
                )
            )

        if source_vm == target_vm:
            raise NetworkDeploymentError(
                "Una VM no puede conectarse consigo misma."
            )

        link_key = canonical_link_key(
            source_vm,
            target_vm,
        )

        if link_key in known_link_keys:
            continue

        known_link_keys.add(
            link_key
        )

        connected_vms.add(
            source_vm
        )

        connected_vms.add(
            target_vm
        )

        segments.append({
            "segment_type": "LINK",
            "link_key": link_key,
            "source_vm": source_vm,
            "target_vm": target_vm,
            "members": [
                source_vm,
                target_vm,
            ],
        })

    for vm_name in vm_names:
        if vm_name in connected_vms:
            continue

        segments.append({
            "segment_type": "ISOLATED",
            "link_key": "isolated--{}".format(
                vm_name
            ),
            "source_vm": vm_name,
            "target_vm": None,
            "members": [
                vm_name,
            ],
        })

    return segments


def get_resource_value(
    resource,
    key,
    default=None,
):
    value = getattr(
        resource,
        key,
        None,
    )

    if value is not None:
        return value

    try:
        data = resource.to_dict()
        return data.get(
            key,
            default,
        )
    except Exception:
        return default


def list_existing_subnet_networks(
    connection,
):
    existing_networks = []

    try:
        for subnet in connection.network.subnets():
            cidr = get_resource_value(
                subnet,
                "cidr",
            )

            if not cidr:
                continue

            try:
                existing_networks.append(
                    ipaddress.ip_network(
                        cidr,
                        strict=False,
                    )
                )
            except ValueError:
                continue

    except Exception as error:
        raise NetworkDeploymentError(
            "No se pudieron consultar las subredes "
            "de Neutron: {}".format(error)
        )

    return existing_networks


def allocate_available_subnets(
    connection,
    count,
    address_pool=DEFAULT_ADDRESS_POOL,
    prefix_length=DEFAULT_PREFIX_LENGTH,
):
    if count <= 0:
        return []

    try:
        address_network = ipaddress.ip_network(
            address_pool,
            strict=False,
        )
    except ValueError:
        raise NetworkDeploymentError(
            "El pool de direcciones es inválido."
        )

    if prefix_length <= address_network.prefixlen:
        raise NetworkDeploymentError(
            "El prefijo de segmento debe ser mayor que "
            "el prefijo del pool."
        )

    existing_networks = list_existing_subnet_networks(
        connection
    )

    selected_networks = []

    for candidate in address_network.subnets(
        new_prefix=prefix_length
    ):
        overlaps = any(
            candidate.overlaps(existing)
            for existing in existing_networks
        )

        if overlaps:
            continue

        selected_networks.append(
            candidate
        )

        existing_networks.append(
            candidate
        )

        if len(selected_networks) == count:
            return selected_networks

    raise NetworkDeploymentError(
        "No existen suficientes subredes libres "
        "en el pool {}.".format(address_pool)
    )


def get_gateway_address(
    subnet_network,
):
    try:
        return str(
            next(subnet_network.hosts())
        )
    except StopIteration:
        raise NetworkDeploymentError(
            "La subred {} no tiene direcciones "
            "utilizables.".format(subnet_network)
        )


def extract_port_ip(
    port,
):
    fixed_ips = get_resource_value(
        port,
        "fixed_ips",
        [],
    )

    if not fixed_ips:
        return None

    first_fixed_ip = fixed_ips[0]

    if isinstance(first_fixed_ip, dict):
        return first_fixed_ip.get(
            "ip_address"
        )

    return getattr(
        first_fixed_ip,
        "ip_address",
        None,
    )


def extract_port_mac(
    port,
):
    return get_resource_value(
        port,
        "mac_address",
        None,
    )


def create_neutron_port(
    connection,
    network_id,
    subnet_id,
    port_name,
):
    port = connection.network.create_port(
        name=port_name,
        network_id=network_id,
        admin_state_up=True,
        fixed_ips=[
            {
                "subnet_id": subnet_id,
            }
        ],
    )

    return {
        "id": port.id,
        "name": get_resource_value(
            port,
            "name",
            port_name,
        ),
        "ip_address": extract_port_ip(
            port
        ),
        "mac_address": extract_port_mac(
            port
        ),
    }


def sanitize_name(
    value,
):
    return "".join(
        character
        if character.isalnum()
        or character in ("-", "_")
        else "_"
        for character in str(value)
    )


def create_segment_network(
    connection,
    slice_name,
    segment,
    subnet_network,
    allocation_index,
):
    safe_slice_name = sanitize_name(
        slice_name
    )

    network_name = "{}-segment-{}".format(
        safe_slice_name,
        allocation_index,
    )

    subnet_name = "{}-subnet".format(
        network_name
    )

    gateway_ip = get_gateway_address(
        subnet_network
    )

    created_network = None
    created_subnet = None
    created_ports = []

    try:
        created_network = (
            connection.network.create_network(
                name=network_name,
                admin_state_up=True,
            )
        )

        created_subnet = (
            connection.network.create_subnet(
                name=subnet_name,
                network_id=created_network.id,
                ip_version=4,
                cidr=str(subnet_network),
                gateway_ip=gateway_ip,
                enable_dhcp=True,
            )
        )

        ports_by_vm = {}

        for vm_name in segment["members"]:
            port_name = "{}-{}-port-{}".format(
                safe_slice_name,
                sanitize_name(vm_name),
                allocation_index,
            )

            port_data = create_neutron_port(
                connection=connection,
                network_id=created_network.id,
                subnet_id=created_subnet.id,
                port_name=port_name,
            )

            port_data["vm_name"] = vm_name

            ports_by_vm[vm_name] = (
                port_data
            )

            created_ports.append(
                port_data
            )

        return {
            "network_id": created_network.id,
            "network_name": network_name,
            "subnet_id": created_subnet.id,
            "subnet_name": subnet_name,
            "cidr": str(subnet_network),
            "gateway": gateway_ip,
            "segment": segment,
            "ports": ports_by_vm,
        }

    except Exception as error:
        for port_data in reversed(
            created_ports
        ):
            try:
                connection.network.delete_port(
                    port_data["id"],
                    ignore_missing=True,
                )
            except Exception:
                pass

        if created_subnet is not None:
            try:
                connection.network.delete_subnet(
                    created_subnet.id,
                    ignore_missing=True,
                )
            except Exception:
                pass

        if created_network is not None:
            try:
                connection.network.delete_network(
                    created_network.id,
                    ignore_missing=True,
                )
            except Exception:
                pass

        raise NetworkDeploymentError(
            "No se pudo crear el segmento '{}': {}"
            .format(
                segment["link_key"],
                error,
            )
        )


def delete_openstack_segment(
    connection,
    deployed_segment,
):
    for port_data in deployed_segment.get(
        "ports",
        {}
    ).values():
        port_id = port_data.get(
            "id"
        )

        if not port_id:
            continue

        try:
            connection.network.delete_port(
                port_id,
                ignore_missing=True,
            )
        except Exception:
            pass

    subnet_id = deployed_segment.get(
        "subnet_id"
    )

    if subnet_id:
        try:
            connection.network.delete_subnet(
                subnet_id,
                ignore_missing=True,
            )
        except Exception:
            pass

    network_id = deployed_segment.get(
        "network_id"
    )

    if network_id:
        try:
            connection.network.delete_network(
                network_id,
                ignore_missing=True,
            )
        except Exception:
            pass


def deploy_slice_networks(
    connection,
    slice_id,
    slice_name,
    topology_data,
    address_pool=DEFAULT_ADDRESS_POOL,
    prefix_length=DEFAULT_PREFIX_LENGTH,
):
    if connection is None:
        raise NetworkDeploymentError(
            "No existe una conexión OpenStack."
        )

    segments = build_network_segments(
        topology_data
    )

    subnet_networks = allocate_available_subnets(
        connection=connection,
        count=len(segments),
        address_pool=address_pool,
        prefix_length=prefix_length,
    )

    deployed_segments = []

    try:
        for allocation_index, segment in enumerate(
            segments,
            start=1,
        ):
            subnet_network = subnet_networks[
                allocation_index - 1
            ]

            gateway_ip = get_gateway_address(
                subnet_network
            )

            local_network_record = (
                create_network_resource_record(
                    slice_id=slice_id,
                    name="{}-segment-{}".format(
                        slice_name,
                        allocation_index,
                    ),
                    link_key=segment["link_key"],
                    allocation_index=allocation_index,
                    cidr=str(subnet_network),
                    gateway=gateway_ip,
                    enable_dhcp=True,
                    status="PENDING",
                )
            )

            try:
                deployed_segment = create_segment_network(
                    connection=connection,
                    slice_name=slice_name,
                    segment=segment,
                    subnet_network=subnet_network,
                    allocation_index=allocation_index,
                )

            except Exception:
                delete_network_resource_record(
                    local_network_record["id"]
                )
                raise

            update_network_resource_openstack(
                network_resource_id=local_network_record[
                    "id"
                ],
                openstack_network_id=deployed_segment[
                    "network_id"
                ],
                openstack_subnet_id=deployed_segment[
                    "subnet_id"
                ],
                status="ACTIVE",
            )

            deployed_segment[
                "network_resource_id"
            ] = local_network_record["id"]

            if segment["segment_type"] == "LINK":
                source_vm = segment[
                    "source_vm"
                ]

                target_vm = segment[
                    "target_vm"
                ]

                source_port_id = (
                    deployed_segment["ports"][
                        source_vm
                    ]["id"]
                )

                target_port_id = (
                    deployed_segment["ports"][
                        target_vm
                    ]["id"]
                )

                slice_link = create_slice_link_record(
                    slice_id=slice_id,
                    network_resource_id=local_network_record[
                        "id"
                    ],
                    source_vm=source_vm,
                    target_vm=target_vm,
                    source_port_id=source_port_id,
                    target_port_id=target_port_id,
                    status="ACTIVE",
                )

                deployed_segment[
                    "slice_link_id"
                ] = slice_link["id"]

            deployed_segments.append(
                deployed_segment
            )

        return deployed_segments

    except Exception:
        rollback_slice_networks(
            connection=connection,
            deployed_segments=deployed_segments,
        )

        raise


def rollback_slice_networks(
    connection,
    deployed_segments,
):
    for deployed_segment in reversed(
        deployed_segments
    ):
        delete_openstack_segment(
            connection=connection,
            deployed_segment=deployed_segment,
        )

        network_resource_id = (
            deployed_segment.get(
                "network_resource_id"
            )
        )

        if network_resource_id:
            try:
                delete_network_resource_record(
                    network_resource_id
                )
            except Exception:
                pass
=== FILE: deployment/vm_deployer.py ===
from database.repositories.network_resource_repository import (
    list_network_resources,
    list_slice_links,
)

from database.repositories.virtual_machine_repository import (
    create_virtual_machine_record,
    delete_virtual_machine_record,
    update_virtual_machine_openstack,
)

from database.repositories.vm_interface_repository import (
    create_vm_interface_record,
)

from deployment.console_manager import (
    generate_novnc_console,
)

from deployment.internet_network_manager import (
    create_internet_port,
)


DEFAULT_SERVER_TIMEOUT = 600


class VMDeploymentError(Exception):
    pass


def get_resource_value(
    resource,
    key,
    default=None,
):
    value = getattr(
        resource,
        key,
        None,
    )

    if value is not None:
        return value

    try:
        data = resource.to_dict()
        return data.get(
            key,
            default,
        )
    except Exception:
        return default


def extract_port_ip(port):
    fixed_ips = get_resource_value(
        port,
        "fixed_ips",
        [],
    )

    if not fixed_ips:
        return None

    first_fixed_ip = fixed_ips[0]

    if isinstance(first_fixed_ip, dict):
        return first_fixed_ip.get(
            "ip_address"
        )

    return getattr(
        first_fixed_ip,
        "ip_address",
        None,
    )


def extract_port_mac(port):
    return get_resource_value(
        port,
        "mac_address",
        None,
    )


def sanitize_name(value):
    return "".join(
        character
        if character.isalnum()
        or character in ("-", "_")
        else "_"
        for character in str(value)
    )


def add_port_mapping(
    port_map,
    vm_name,
    network_resource_id,
    port_id,
    interface_type="TOPOLOGY",
):
    if not port_id:
        return

    port_map.setdefault(
        vm_name,
        [],
    )

    already_added = any(
        item["port_id"] == port_id
        for item in port_map[vm_name]
    )

    if already_added:
        return

    port_map[vm_name].append({
        "network_resource_id":
            network_resource_id,
        "port_id": port_id,
        "interface_type": interface_type,
    })


def build_vm_port_map(
    connection,
    slice_id,
):
    """
    Construye el mapa de puertos de topología:

    {
        "vm1": [
            {
                "network_resource_id": 1,
                "port_id": "...",
                "interface_type": "TOPOLOGY",
            }
        ]
    }

    La interfaz de Internet se añade posteriormente,
    durante el despliegue de cada VM.
    """

    network_resources = list_network_resources(
        slice_id
    )

    slice_links = list_slice_links(
        slice_id
    )

    networks_by_id = {
        record["id"]: record
        for record in network_resources
    }

    port_map = {}

    for link in slice_links:
        add_port_mapping(
            port_map=port_map,
            vm_name=link["source_vm"],
            network_resource_id=link[
                "network_resource_id"
            ],
            port_id=link[
                "source_port_id"
            ],
            interface_type="TOPOLOGY",
        )

        add_port_mapping(
            port_map=port_map,
            vm_name=link["target_vm"],
            network_resource_id=link[
                "network_resource_id"
            ],
            port_id=link[
                "target_port_id"
            ],
            interface_type="TOPOLOGY",
        )

    # Las VMs aisladas también tienen un puerto de topología.
    for network_record in network_resources:
        link_key = str(
            network_record.get(
                "link_key",
                "",
            )
        )

        if not link_key.startswith(
            "isolated--"
        ):
            continue

        vm_name = link_key.split(
            "isolated--",
            1,
        )[1]

        network_id = network_record.get(
            "openstack_network_id"
        )

        if not network_id:
            continue

        ports = connection.network.ports(
            network_id=network_id
        )

        for port in ports:
            add_port_mapping(
                port_map=port_map,
                vm_name=vm_name,
                network_resource_id=network_record[
                    "id"
                ],
                port_id=port.id,
                interface_type="TOPOLOGY",
            )

    allocation_by_network = {
        network_id: record[
            "allocation_index"
        ]
        for network_id, record
        in networks_by_id.items()
    }

    for vm_name in port_map:
        port_map[vm_name].sort(
            key=lambda item: allocation_by_network.get(
                item["network_resource_id"],
                999999,
            )
        )

    return port_map


def wait_for_server_active(
    connection,
    server,
    timeout=DEFAULT_SERVER_TIMEOUT,
):
    try:
        return connection.compute.wait_for_server(
            server,
            status="ACTIVE",
            failures=[
                "ERROR",
            ],
            interval=2,
            wait=timeout,
        )

    except Exception as error:
        raise VMDeploymentError(
            "La VM '{}' no alcanzó estado ACTIVE: {}"
            .format(
                getattr(
                    server,
                    "name",
                    server.id,
                ),
                error,
            )
        )


def get_actual_server_host(server):
    possible_keys = (
        "OS-EXT-SRV-ATTR:host",
        "hypervisor_hostname",
        "host",
    )

    for key in possible_keys:
        value = get_resource_value(
            server,
            key,
            None,
        )

        if value:
            return str(value)

    return None


def create_nova_server(
    connection,
    server_name,
    assignment,
    port_ids,
):
    networks = [
        {
            "port": port_id,
        }
        for port_id in port_ids
    ]

    if not networks:
        raise VMDeploymentError(
            "La VM '{}' no tiene puertos asignados."
            .format(
                assignment["vm_name"]
            )
        )

    requested_availability_zone = assignment.get(
        "availability_zone"
    )

    # Evita enviar "nova:worker1", porque eso fuerza el host
    # y un usuario normal normalmente no tiene ese permiso.
    scheduler_availability_zone = None

    if requested_availability_zone:
        scheduler_availability_zone = str(
            requested_availability_zone
        ).split(":", 1)[0]

    server_arguments = {
        "name": server_name,
        "image_id": assignment["image_id"],
        "flavor_id": assignment["flavor_id"],
        "networks": networks,
    }

    if scheduler_availability_zone:
        server_arguments["availability_zone"] = (
            scheduler_availability_zone
        )

    try:
        return connection.compute.create_server(
            **server_arguments
        )

    except Exception as error:
        raise VMDeploymentError(
            "No se pudo crear la VM '{}': {}"
            .format(
                assignment["vm_name"],
                error,
            )
        )


def refresh_port_data(
    connection,
    port_id,
):
    port = connection.network.get_port(
        port_id
    )

    if port is None:
        raise VMDeploymentError(
            "No se encontró el puerto {}."
            .format(port_id)
        )

    return {
        "port_id": port.id,
        "ip_address": extract_port_ip(
            port
        ),
        "mac_address": extract_port_mac(
            port
        ),
        "status": str(
            get_resource_value(
                port,
                "status",
                "DOWN",
            )
        ).upper(),
    }


def delete_port_safely(
    connection,
    port_id,
):
    if not port_id:
        return

    try:
        connection.network.delete_port(
            port_id,
            ignore_missing=True,
        )
    except Exception:
        pass


def deploy_slice_virtual_machines(
    connection,
    slice_id,
    slice_name,
    placement_plan,
    timeout=DEFAULT_SERVER_TIMEOUT,
):
    if connection is None:
        raise VMDeploymentError(
            "No existe una conexión OpenStack."
        )

    if not placement_plan.get(
        "success",
        False,
    ):
        raise VMDeploymentError(
            "El Placement Plan está incompleto."
        )

    assignments = placement_plan.get(
        "assignments",
        [],
    )

    if not assignments:
        raise VMDeploymentError(
            "El Placement Plan no contiene VMs."
        )

    vm_port_map = build_vm_port_map(
        connection=connection,
        slice_id=slice_id,
    )

    deployed_vms = []

    try:
        for assignment in assignments:
            vm_name = assignment[
                "vm_name"
            ]

            # Copia la lista para no modificar el mapa original.
            port_records = list(
                vm_port_map.get(
                    vm_name,
                    [],
                )
            )

            # Crea automáticamente una interfaz adicional
            # de Internet/gestión para cada VM.
            internet_port = create_internet_port(
                connection=connection,
                vm_name=vm_name,
                slice_name=slice_name,
            )

            port_records.append({
                "network_resource_id": None,
                "port_id": internet_port["id"],
                "interface_type": "INTERNET",
            })

            if not port_records:
                raise VMDeploymentError(
                    "No existen puertos para la VM '{}'."
                    .format(vm_name)
                )

            local_vm = create_virtual_machine_record(
                slice_id=slice_id,
                name=vm_name,
                image_id=assignment["image_id"],
                flavor_id=assignment["flavor_id"],
                worker=assignment["worker"],
                availability_zone=assignment[
                    "availability_zone"
                ],
                status="PENDING",
            )

            server_name = "{}-{}".format(
                sanitize_name(slice_name),
                sanitize_name(vm_name),
            )

            server = None

            try:
                update_virtual_machine_openstack(
                    virtual_machine_id=local_vm["id"],
                    status="BUILD",
                )

                server = create_nova_server(
                    connection=connection,
                    server_name=server_name,
                    assignment=assignment,
                    port_ids=[
                        item["port_id"]
                        for item in port_records
                    ],
                )

                update_virtual_machine_openstack(
                    virtual_machine_id=local_vm["id"],
                    openstack_server_id=server.id,
                    status="BUILD",
                )

                server = wait_for_server_active(
                    connection=connection,
                    server=server,
                    timeout=timeout,
                )

                actual_worker = (
                    get_actual_server_host(server)
                    or assignment["worker"]
                )

                requested_zone = str(
                    assignment.get(
                        "availability_zone",
                        "nova",
                    )
                ).split(":", 1)[0]

                update_virtual_machine_openstack(
                    virtual_machine_id=local_vm["id"],
                    openstack_server_id=server.id,
                    worker=actual_worker,
                    availability_zone=requested_zone,
                    status="ACTIVE",
                )

                interfaces = []

                for interface_index, port_record in enumerate(
                    port_records
                ):
                    port_data = refresh_port_data(
                        connection=connection,
                        port_id=port_record[
                            "port_id"
                        ],
                    )

                    interface_type = port_record.get(
                        "interface_type",
                        "TOPOLOGY",
                    )

                    interface = create_vm_interface_record(
                        virtual_machine_id=local_vm["id"],
                        network_resource_id=port_record.get(
                            "network_resource_id"
                        ),
                        openstack_port_id=port_data[
                            "port_id"
                        ],
                        ip_address=port_data[
                            "ip_address"
                        ],
                        mac_address=port_data[
                            "mac_address"
                        ],
                        interface_index=interface_index,
                        interface_type=interface_type,
                        status=port_data[
                            "status"
                        ],
                    )

                    interfaces.append(
                        interface
                    )

                # Genera una consola temporal al finalizar.
                # Si falla noVNC, la VM continúa desplegada.
                try:
                    console_data = generate_novnc_console(
                        connection=connection,
                        server_id=server.id,
                    )

                except Exception as console_error:
                    console_data = {
                        "url": None,
                        "error": str(
                            console_error
                        ),
                    }

                deployed_vms.append({
                    "local_vm_id": local_vm["id"],
                    "vm_name": vm_name,
                    "server_name": server_name,
                    "server_id": server.id,
                    "worker": actual_worker,
                    "status": "ACTIVE",
                    "interfaces": interfaces,
                    "console": console_data,
                })

            except Exception:
                if server is not None:
                    try:
                        connection.compute.delete_server(
                            server.id,
                            ignore_missing=True,
                        )
                    except Exception:
                        pass

                # El puerto de Internet fue creado fuera del
                # conjunto de redes del slice, así que debe
                # limpiarse explícitamente si esta VM falla.
                delete_port_safely(
                    connection=connection,
                    port_id=internet_port.get(
                        "id"
                    ),
                )

                try:
                    update_virtual_machine_openstack(
                        virtual_machine_id=local_vm["id"],
                        status="ERROR",
                    )
                except Exception:
                    pass

                raise

        return deployed_vms

    except Exception:
        rollback_slice_virtual_machines(
            connection=connection,
            deployed_vms=deployed_vms,
        )

        raise


def rollback_slice_virtual_machines(
    connection,
    deployed_vms,
):
    for deployed_vm in reversed(
        deployed_vms
    ):
        server_id = deployed_vm.get(
            "server_id"
        )

        if server_id:
            try:
                connection.compute.delete_server(
                    server_id,
                    ignore_missing=True,
                )
            except Exception:
                pass

        # Elimina puertos registrados en las interfaces.
        for interface in deployed_vm.get(
            "interfaces",
            [],
        ):
            port_id = interface.get(
                "openstack_port_id"
            )

            delete_port_safely(
                connection=connection,
                port_id=port_id,
            )

        local_vm_id = deployed_vm.get(
            "local_vm_id"
        )

        if local_vm_id:
            try:
                delete_virtual_machine_record(
                    local_vm_id
                )
            except Exception:
                pass
=== FILE: slices/slice_manager.py ===
import time

from database.connection import get_db_session
from database.models import (
    NetworkResource,
    Slice,
    SliceLink,
    VirtualMachine,
    VirtualMachineInterface,
)

from database.repositories.slice_repository import (
    create_slice_record,
    get_slice_by_id,
    list_slice_records,
    update_slice_status,
)

from database.repositories.topology_repository import (
    get_topology,
    list_topologies,
)

from database.repositories.virtual_machine_repository import (
    list_virtual_machines,
)

from database.repositories.vm_interface_repository import (
    list_vm_interfaces,
)

from deployment.network_deployer import (
    deploy_slice_networks,
    rollback_slice_networks,
)

from deployment.vm_deployer import (
    deploy_slice_virtual_machines,
    rollback_slice_virtual_machines,
)

from placement.placement_manager import (
    generate_placement_plan,
)


class SliceManagerError(Exception):
    pass


# ============================================================
# CONTEXTO Y PERMISOS
# ============================================================

def get_slice_context(session_context):
    if session_context is None:
        raise SliceManagerError(
            "No existe una sesión autenticada."
        )

    required_fields = (
        "local_user_id",
        "local_project_id",
        "openstack_project_id",
        "role",
        "connection",
    )

    missing = [
        field
        for field in required_fields
        if session_context.get(field) is None
    ]

    if missing:
        raise SliceManagerError(
            "La sesión no contiene: {}".format(
                ", ".join(missing)
            )
        )

    return {
        "owner_id":
            session_context["local_user_id"],

        "project_id":
            session_context["local_project_id"],

        "openstack_project_id":
            session_context["openstack_project_id"],

        "project_name":
            session_context.get("project_name"),

        "role": str(
            session_context["role"]
        ).strip().lower(),

        "connection":
            session_context["connection"],
    }


def can_modify_slice(
    session_context,
    slice_record,
):
    context = get_slice_context(
        session_context
    )

    if context["role"] == "superadmin":
        return True

    return (
        slice_record["project_id"]
        == context["project_id"]
        and slice_record["owner_id"]
        == context["owner_id"]
    )


def can_delete_slice(
    session_context,
    slice_record,
):
    context = get_slice_context(
        session_context
    )

    if context["role"] == "superadmin":
        return True

    if context["role"] == "admin":
        return False

    return (
        context["role"] == "user"
        and slice_record["project_id"]
        == context["project_id"]
        and slice_record["owner_id"]
        == context["owner_id"]
    )


# ============================================================
# TOPOLOGÍAS DISPONIBLES PARA DESPLEGAR
# ============================================================

def list_deployable_topologies(
    session_context,
):
    context = get_slice_context(
        session_context
    )

    records = list_topologies(
        owner_id=context["owner_id"],
        project_id=context["project_id"],
        role=context["role"],
    )

    result = []

    for topology in records:
        if str(
            topology.get("status", "")
        ).upper() != "READY":
            continue

        # Superadmin puede desplegar cualquier topología
        # visible del proyecto actual.
        if context["role"] == "superadmin":
            if (
                topology["project_id"]
                == context["project_id"]
            ):
                result.append(topology)

            continue

        # Admin y user solo despliegan las suyas.
        if (
            topology["project_id"]
            == context["project_id"]
            and topology["owner_id"]
            == context["owner_id"]
        ):
            result.append(topology)

    return result


# ============================================================
# DESPLIEGUE COMPLETO
# ============================================================

def deploy_topology_as_slice(
    session_context,
    topology_id,
    slice_name,
):
    context = get_slice_context(
        session_context
    )

    topology = get_topology(
        topology_id=topology_id,
        owner_id=context["owner_id"],
        project_id=context["project_id"],
        role=context["role"],
    )

    if topology is None:
        raise SliceManagerError(
            "La topología no existe o no es visible."
        )

    if str(
        topology["status"]
    ).upper() != "READY":
        raise SliceManagerError(
            "Solo se pueden desplegar topologías READY."
        )

    if context["role"] != "superadmin":
        if topology["owner_id"] != context["owner_id"]:
            raise PermissionError(
                "Solo puede desplegar sus propias topologías."
            )

    if topology["project_id"] != context["project_id"]:
        raise PermissionError(
            "La topología no pertenece al proyecto actual."
        )

    slice_record = None
    deployed_networks = []
    deployed_vms = []

    try:
        slice_record = create_slice_record(
            name=slice_name,
            topology_id=topology_id,
            owner_id=topology["owner_id"],
            project_id=context["project_id"],
            openstack_project_id=context[
                "openstack_project_id"
            ],
            platform="openstack",
        )

        update_slice_status(
            slice_id=slice_record["id"],
            status="PLANNING",
        )

        placement_plan = generate_placement_plan(
            session_context=session_context,
            topology_id=topology_id,
        )

        if not placement_plan["success"]:
            raise SliceManagerError(
                "El Placement no pudo ubicar todas las VMs."
            )

        update_slice_status(
            slice_id=slice_record["id"],
            status="DEPLOYING_NETWORKS",
        )

        deployed_networks = deploy_slice_networks(
            connection=context["connection"],
            slice_id=slice_record["id"],
            slice_name=slice_name,
            topology_data=topology["topology_data"],
        )

        update_slice_status(
            slice_id=slice_record["id"],
            status="DEPLOYING_VMS",
        )

        deployed_vms = deploy_slice_virtual_machines(
            connection=context["connection"],
            slice_id=slice_record["id"],
            slice_name=slice_name,
            placement_plan=placement_plan,
            timeout=600,
        )

        final_record = update_slice_status(
            slice_id=slice_record["id"],
            status="RUNNING",
            error_message=None,
        )

        return {
            "slice": final_record,
            "placement_plan": placement_plan,
            "networks": deployed_networks,
            "virtual_machines": deployed_vms,
        }

    except Exception as error:
        if deployed_vms:
            try:
                rollback_slice_virtual_machines(
                    connection=context["connection"],
                    deployed_vms=deployed_vms,
                )
            except Exception:
                pass

        if deployed_networks:
            try:
                rollback_slice_networks(
                    connection=context["connection"],
                    deployed_segments=deployed_networks,
                )
            except Exception:
                pass

        if slice_record is not None:
            try:
                update_slice_status(
                    slice_id=slice_record["id"],
                    status="ERROR",
                    error_message=str(error),
                )
            except Exception:
                pass

        raise


# ============================================================
# LISTADO Y DETALLE
# ============================================================

def get_visible_slices(
    session_context,
):
    context = get_slice_context(
        session_context
    )

    return list_slice_records(
        owner_id=context["owner_id"],
        project_id=context["project_id"],
        role=context["role"],
        include_deleted=False,
    )


def get_visible_slice(
    session_context,
    slice_id,
):
    visible_slices = get_visible_slices(
        session_context
    )

    visible_ids = {
        record["id"]
        for record in visible_slices
    }

    if slice_id not in visible_ids:
        return None

    return get_slice_by_id(
        slice_id
    )


def get_slice_detail(
    session_context,
    slice_id,
):
    slice_record = get_visible_slice(
        session_context=session_context,
        slice_id=slice_id,
    )

    if slice_record is None:
        return None

    virtual_machines = list_virtual_machines(
        slice_id
    )

    vm_details = []

    for vm in virtual_machines:
        vm_data = dict(vm)

        vm_data["interfaces"] = list_vm_interfaces(
            vm["id"]
        )

        vm_details.append(
            vm_data
        )

    session = get_db_session()

    try:
        networks = (
            session.query(NetworkResource)
            .filter(
                NetworkResource.slice_id == slice_id
            )
            .order_by(
                NetworkResource.allocation_index.asc()
            )
            .all()
        )

        links = (
            session.query(SliceLink)
            .filter(
                SliceLink.slice_id == slice_id
            )
            .order_by(SliceLink.id.asc())
            .all()
        )

        network_data = [
            {
                "id": record.id,
                "name": record.name,
                "link_key": record.link_key,
                "cidr": record.cidr,
                "gateway": record.gateway,
                "status": record.status,
                "openstack_network_id":
                    record.openstack_network_id,
                "openstack_subnet_id":
                    record.openstack_subnet_id,
            }
            for record in networks
        ]

        link_data = [
            {
                "id": record.id,
                "source_vm": record.source_vm,
                "target_vm": record.target_vm,
                "source_port_id":
                    record.source_port_id,
                "target_port_id":
                    record.target_port_id,
                "status": record.status,
            }
            for record in links
        ]

    finally:
        session.close()

    return {
        "slice": slice_record,
        "virtual_machines": vm_details,
        "networks": network_data,
        "links": link_data,
    }


# ============================================================
# EDICIÓN BÁSICA
# ============================================================

def rename_slice(
    session_context,
    slice_id,
    new_name,
):
    slice_record = get_visible_slice(
        session_context=session_context,
        slice_id=slice_id,
    )

    if slice_record is None:
        raise SliceManagerError(
            "El slice no existe o no es visible."
        )

    if not can_modify_slice(
        session_context,
        slice_record,
    ):
        raise PermissionError(
            "No tiene permisos para editar este slice."
        )

    new_name = str(
        new_name
    ).strip()

    if not new_name:
        raise ValueError(
            "El nuevo nombre es obligatorio."
        )

    session = get_db_session()

    try:
        duplicated = (
            session.query(Slice)
            .filter(
                Slice.project_id
                == slice_record["project_id"],

                Slice.name == new_name,
                Slice.id != slice_id,
            )
            .first()
        )

        if duplicated is not None:
            raise ValueError(
                "Ya existe otro slice con ese nombre."
            )

        record = session.query(
            Slice
        ).get(slice_id)

        record.name = new_name

        session.commit()
        session.refresh(record)

        return get_slice_by_id(
            slice_id
        )

    except Exception:
        session.rollback()
        raise

    finally:
        session.close()


def wait_server_deleted(
    connection,
    server_id,
    timeout=120,
):
    start_time = time.time()

    while time.time() - start_time <= timeout:
        server = connection.compute.get_server(
            server_id
        )

        if server is None:
            return True

        time.sleep(2)

    return False


def delete_vm_from_slice(
    session_context,
    slice_id,
    virtual_machine_id,
):
    context = get_slice_context(
        session_context
    )

    slice_record = get_visible_slice(
        session_context=session_context,
        slice_id=slice_id,
    )

    if slice_record is None:
        raise SliceManagerError(
            "El slice no existe o no es visible."
        )

    if not can_modify_slice(
        session_context,
        slice_record,
    ):
        raise PermissionError(
            "No tiene permisos para editar este slice."
        )

    if slice_record["status"] != "RUNNING":
        raise SliceManagerError(
            "Solo se pueden editar slices RUNNING."
        )

    session = get_db_session()

    try:
        vm_record = (
            session.query(VirtualMachine)
            .filter(
                VirtualMachine.id
                == virtual_machine_id,

                VirtualMachine.slice_id
                == slice_id,
            )
            .first()
        )

        if vm_record is None:
            raise ValueError(
                "La VM no pertenece al slice."
            )

        server_id = vm_record.openstack_server_id

        interfaces = list(
            vm_record.interfaces
        )

        update_slice_status(
            slice_id=slice_id,
            status="UPDATING",
        )

        if server_id:
            context["connection"].compute.delete_server(
                server_id,
                ignore_missing=True,
            )

            wait_server_deleted(
                connection=context["connection"],
                server_id=server_id,
            )

        # Al eliminar Nova, los puertos precreados pueden
        # continuar existiendo. Se eliminan explícitamente.
        for interface in interfaces:
            try:
                context["connection"].network.delete_port(
                    interface.openstack_port_id,
                    ignore_missing=True,
                )
            except Exception:
                pass

        session.delete(vm_record)
        session.commit()

        update_slice_status(
            slice_id=slice_id,
            status="RUNNING",
            error_message=None,
        )

        return True

    except Exception as error:
        session.rollback()

        try:
            update_slice_status(
                slice_id=slice_id,
                status="ERROR",
                error_message=str(error),
            )
        except Exception:
            pass

        raise

    finally:
        session.close()


# ============================================================
# ELIMINACIÓN COMPLETA
# ============================================================

def clear_slice_local_resources(
    slice_id,
):
    session = get_db_session()

    try:
        session.query(
            VirtualMachineInterface
        ).filter(
            VirtualMachineInterface.virtual_machine_id.in_(
                session.query(VirtualMachine.id).filter(
                    VirtualMachine.slice_id == slice_id
                )
            )
        ).delete(
            synchronize_session=False
        )

        session.query(
            VirtualMachine
        ).filter(
            VirtualMachine.slice_id == slice_id
        ).delete(
            synchronize_session=False
        )

        session.query(
            SliceLink
        ).filter(
            SliceLink.slice_id == slice_id
        ).delete(
            synchronize_session=False
        )

        session.query(
            NetworkResource
        ).filter(
            NetworkResource.slice_id == slice_id
        ).delete(
            synchronize_session=False
        )

        session.commit()

    except Exception:
        session.rollback()
        raise

    finally:
        session.close()


def delete_slice_complete(
    session_context,
    slice_id,
):
    context = get_slice_context(
        session_context
    )

    slice_record = get_visible_slice(
        session_context=session_context,
        slice_id=slice_id,
    )

    if slice_record is None:
        raise SliceManagerError(
            "El slice no existe o no es visible."
        )

    if not can_delete_slice(
        session_context,
        slice_record,
    ):
        raise PermissionError(
            "No tiene permisos para eliminar este slice."
        )

    update_slice_status(
        slice_id=slice_id,
        status="DELETING",
    )

    session = get_db_session()

    try:
        virtual_machines = (
            session.query(VirtualMachine)
            .filter(
                VirtualMachine.slice_id == slice_id
            )
            .all()
        )

        networks = (
            session.query(NetworkResource)
            .filter(
                NetworkResource.slice_id == slice_id
            )
            .order_by(
                NetworkResource.allocation_index.desc()
            )
            .all()
        )

        # 1. Eliminar servidores.
        for vm in virtual_machines:
            if not vm.openstack_server_id:
                continue

            try:
                context["connection"].compute.delete_server(
                    vm.openstack_server_id,
                    ignore_missing=True,
                )

                wait_server_deleted(
                    connection=context["connection"],
                    server_id=vm.openstack_server_id,
                )

            except Exception:
                pass

        # 2. Eliminar puertos.
        for vm in virtual_machines:
            for interface in vm.interfaces:
                try:
                    context[
                        "connection"
                    ].network.delete_port(
                        interface.openstack_port_id,
                        ignore_missing=True,
                    )
                except Exception:
                    pass

        # 3. Eliminar subredes y redes.
        for network in networks:
            if network.openstack_subnet_id:
                try:
                    context[
                        "connection"
                    ].network.delete_subnet(
                        network.openstack_subnet_id,
                        ignore_missing=True,
                    )
                except Exception:
                    pass

            if network.openstack_network_id:
                try:
                    context[
                        "connection"
                    ].network.delete_network(
                        network.openstack_network_id,
                        ignore_missing=True,
                    )
                except Exception:
                    pass

    finally:
        session.close()

    clear_slice_local_resources(
        slice_id
    )

    return update_slice_status(
        slice_id=slice_id,
        status="DELETED",
        error_message=None,
    )
=== FILE: common/admin_connection.py ===
import os

import openstack


def get_admin_connection():
    required_variables = (
        "OS_AUTH_URL",
        "OS_USERNAME",
        "OS_PASSWORD",
    )

    missing = [
        variable
        for variable in required_variables
        if not os.environ.get(variable)
    ]

    if missing:
        raise RuntimeError(
            "Faltan variables de OpenStack: {}. "
            "Ejecute primero: "
            "source /root/env-scripts/admin-openrc".format(
                ", ".join(missing)
            )
        )

    try:
        connection = openstack.connect()
        connection.authorize()

        return connection

    except Exception as error:
        raise RuntimeError(
            "No se pudo crear la conexión administrativa "
            "con OpenStack: {}".format(error)