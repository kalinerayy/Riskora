"""Funções auxiliares dos testes (sem fixtures, para facilitar a leitura)."""
from datetime import datetime, timedelta, timezone

from config.settings import Settings
from database.connection import get_connection, init_database
from models.assessment import Answer
from models.user import ROLE_PERMISSIONS, Context
from services.asset_service import AssetService
from services.assessment_service import AssessmentService
from services.authentication_service import AuthenticationService
from services.organization_service import OrganizationService
from services.password_hasher import ScryptHasher

FAST = ScryptHasher(n=2 ** 10)  # custo baixo só nos testes
PASSWORD = "senha-forte-123"
IMPACTS = {"impact_availability": 5, "impact_integrity": 4, "impact_operational": 4, "impact_financial": 3,
           "impact_legal": 2}


def new_db():
    conn = get_connection(":memory:")
    init_database(conn)
    return conn


class Clock:
    """Relógio controlável para simular expiração de sessão e fim de bloqueio."""
    def __init__(self):
        self.now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.now

    def advance(self, **kwargs):
        self.now += timedelta(**kwargs)


def make_auth(conn, clock=None, **overrides):
    settings = Settings(db_path=":memory:", scrypt_n=2 ** 10, **overrides)
    return AuthenticationService(conn, settings=settings, hasher=FAST, clock=clock or Clock())


def make_org(conn, slug="org-a", name="Org A"):
    return OrganizationService(conn).create_organization(name, slug)


def make_user(conn, org_id, email, role="analyst", password=PASSWORD, auth=None):
    """Cria usuário + vínculo diretamente (ignora serviços, para montar cenários de teste)."""
    from database.repositories.accounts import AccountRepository
    auth = auth or make_auth(conn)
    repo = AccountRepository(conn)
    with conn:
        existing = repo.get_user_by_email(email)
        user_id = existing["id"] if existing else repo.create_user(email, email.split("@")[0], auth.hash_password(password))
        repo.add_member(org_id, user_id, role)
    return user_id


def ctx_for(org_id, role="admin", user_id=None, email="u@test.com"):
    """Contexto construído direto do perfil (equivale ao que o login produz)."""
    return Context(user_id, email, "Usuário Teste", org_id, role, ROLE_PERMISSIONS[role])


def answers_of(**kwargs) -> dict:
    out = {}
    for code, v in kwargs.items():
        value, just, ev = (v, "", "") if isinstance(v, str) else v
        out[code] = Answer(code, value, just, ev)
    return out


def backup_asset(conn, ctx, name="Backup ERP", impacts=None, **extra):
    data = {"name": name, "category_code": "backup_recuperacao", **(IMPACTS if impacts is None else impacts), **extra}
    return AssetService(conn).create_asset(ctx, data)


def finalized(conn, ctx, answers: dict, impacts=None, name="Backup ERP"):
    """Cria ativo de backup + avaliação com as respostas e a conclui. Devolve (asset_id, assessment_id, service)."""
    asset_id = backup_asset(conn, ctx, name, impacts)
    svc = AssessmentService(conn)
    aid = svc.create_assessment(ctx, asset_id)
    for code, value in answers.items():
        svc.save_answer(ctx, aid, code, value, "obs" if value == "nao_se_aplica" else "")
    svc.finalize_assessment(ctx, aid)
    return asset_id, aid, svc
