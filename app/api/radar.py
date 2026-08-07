"""
License Server - Radar de Publicações
Endpoint público de auto-emissão de licença, uma por inscrição da OAB.

ISOLAMENTO — leia antes de mexer
---------------------------------
A tabela `licenses` é compartilhada com os sistemas que já estão em produção
(enterprise_system e os demais). Este módulo NÃO altera o esquema e NÃO toca em
nenhum registro existente. A separação é feita por dados:

  * todas as licenças do Radar pendem de UM único Client, identificado por
    `metadata.produto == "radar"`;
  * cada licença carrega `metadata.produto = "radar"` e a inscrição da OAB.

Para listar só as do Radar, no painel ou no banco:

    SELECT * FROM licenses WHERE metadata->>'produto' = 'radar';

Nada mais do servidor muda de comportamento. Uma coluna `product` seria mais
elegante, mas exigiria migração num banco de produção multi-sistema — troca
ruim por elegância.

SEGURANÇA
---------
O endpoint é público porque o aplicativo é distribuído e não pode carregar um
segredo: qualquer chave embutida num .exe é extraível. Em compensação, ele é
estreito de propósito — só cria licença sob o Client do Radar, com plano e
prazo fixos no código. Não lê, não altera e não apaga nada de outro produto.

É idempotente por (OAB, UF): reinstalar o aplicativo ou recadastrar a mesma
inscrição devolve a MESMA chave, em vez de multiplicar registros.
"""
from datetime import datetime
import logging
import re

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import generate_license_key
from app.database import get_db
from app.models import Client, License, LicenseStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/radar/v1", tags=["Radar de Publicações"])

PRODUTO = "radar"

# O Client agregador das licenças do Radar. Criado sob demanda, uma única vez.
CLIENT_NOME = "Radar de Publicações — usuários"
CLIENT_EMAIL = "radar@promptjuridico.com.br"

# `licenses.expires_at` é NOT NULL, então "sem vencimento" é uma data distante.
# O ano 2099 deixa evidente, para quem olhar o banco, que é sentinela e não um
# prazo real.
SEM_VENCIMENTO = datetime(2099, 12, 31, 23, 59, 59)

# Enquanto o aplicativo é gratuito, nada é limitado. Os campos de limite existem
# para o enterprise_system; aqui ficam altos e sem efeito.
LIMITES_LIVRES = {
    "max_users": 999,
    "max_customers": 999999,
    "max_products": 999999,
    "max_monthly_transactions": 999999,
}

_SO_DIGITOS = re.compile(r"\D")


class LicencaRadarRequest(BaseModel):
    """Pedido de licença para uma inscrição da OAB."""

    numero_oab: str = Field(..., max_length=20)
    uf_oab: str = Field(..., min_length=2, max_length=2)
    hardware_id: str = Field("", max_length=64)
    app_version: str = Field("", max_length=20)


class LicencaRadarResponse(BaseModel):
    license_key: str
    status: str
    plan: str
    oab: str
    nova: bool
    message: str


def _normalizar(numero: str, uf: str) -> tuple[str, str]:
    """Mesma normalização do aplicativo: dígitos sem zeros à esquerda, UF maiúscula."""
    return _SO_DIGITOS.sub("", numero or "").lstrip("0"), (uf or "").strip().upper()


async def _client_do_radar(db: AsyncSession) -> Client:
    """Devolve o Client agregador, criando-o na primeira chamada."""
    resultado = await db.execute(select(Client).where(Client.email == CLIENT_EMAIL))
    cliente = resultado.scalar_one_or_none()
    if cliente:
        return cliente

    cliente = Client(
        name=CLIENT_NOME,
        email=CLIENT_EMAIL,
        document=None,
        contact_name="PromptJurídico",
        country="Brasil",
        is_active=True,
        notes="Agregador das licenças gratuitas do Radar de Publicações.",
        metadata_={"produto": PRODUTO},
    )
    db.add(cliente)
    await db.flush()
    logger.info("Client do Radar criado: %s", cliente.id)
    return cliente


@router.post("/licenca", response_model=LicencaRadarResponse)
async def emitir_licenca(
    dados: LicencaRadarRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Emite (ou devolve) a licença gratuita de uma inscrição da OAB."""
    numero, uf = _normalizar(dados.numero_oab, dados.uf_oab)
    if not numero or len(uf) != 2:
        return LicencaRadarResponse(
            license_key="", status="error", plan="", oab="", nova=False,
            message="Informe o número da OAB e a UF.",
        )

    oab = f"{numero}/{uf}"
    cliente = await _client_do_radar(db)

    # Idempotência: a mesma inscrição sempre recebe a mesma chave. Sem isto,
    # reinstalar o aplicativo encheria a tabela de licenças órfãs.
    resultado = await db.execute(
        select(License).where(
            License.client_id == cliente.id,
            License.metadata_["oab"].as_string() == oab,
        )
    )
    licenca = resultado.scalar_one_or_none()

    if licenca:
        # Só atualizamos sinais de vida — nada de reemitir chave.
        licenca.last_validated_at = datetime.utcnow()
        if dados.hardware_id and not licenca.hardware_id:
            licenca.hardware_id = dados.hardware_id
        await db.commit()
        return LicencaRadarResponse(
            license_key=licenca.license_key, status=licenca.status,
            plan=licenca.plan, oab=oab, nova=False,
            message="Licença já emitida para esta inscrição.",
        )

    licenca = License(
        license_key=generate_license_key(),
        client_id=cliente.id,
        hardware_id=dados.hardware_id or None,
        plan="unlimited",
        features=["radar_publicacoes"],
        issued_at=datetime.utcnow(),
        activated_at=datetime.utcnow(),
        expires_at=SEM_VENCIMENTO,
        status=LicenseStatus.ACTIVE.value,
        is_trial=False,
        notes="Radar de Publicações — licença gratuita (beta).",
        metadata_={
            "produto": PRODUTO,
            "oab": oab,
            "numero_oab": numero,
            "uf_oab": uf,
            "app_version": dados.app_version,
            "emitida_em": datetime.utcnow().isoformat(timespec="seconds"),
        },
        **LIMITES_LIVRES,
    )
    db.add(licenca)
    await db.commit()

    logger.info("Licença do Radar emitida para OAB %s", oab)
    return LicencaRadarResponse(
        license_key=licenca.license_key, status=licenca.status,
        plan=licenca.plan, oab=oab, nova=True,
        message="Licença emitida.",
    )


@router.get("/stats")
async def estatisticas(db: AsyncSession = Depends(get_db)):
    """Contagem das licenças do Radar, para o painel.

    Público e somente-leitura: devolve apenas números agregados deste produto,
    nada de chaves nem de dados de outros sistemas.
    """
    linhas = await db.execute(select(License).join(Client).where(
        Client.email == CLIENT_EMAIL
    ))
    licencas = [
        lic for lic in linhas.scalars().all()
        if (lic.metadata_ or {}).get("produto") == PRODUTO
    ]
    ufs = {
        (lic.metadata_ or {}).get("uf_oab")
        for lic in licencas
        if (lic.metadata_ or {}).get("uf_oab")
    }
    return {
        "produto": PRODUTO,
        "total": len(licencas),
        "ativas": sum(1 for lic in licencas if lic.status == LicenseStatus.ACTIVE.value),
        "estados": len(ufs),
        "maquinas": len({lic.hardware_id for lic in licencas if lic.hardware_id}),
    }


@router.get("/licenca/{license_key}", response_model=LicencaRadarResponse)
async def consultar_licenca(license_key: str, db: AsyncSession = Depends(get_db)):
    """Confere uma licença do Radar. Só enxerga licenças deste produto."""
    resultado = await db.execute(
        select(License).where(License.license_key == license_key)
    )
    licenca = resultado.scalar_one_or_none()

    if not licenca or (licenca.metadata_ or {}).get("produto") != PRODUTO:
        return LicencaRadarResponse(
            license_key=license_key, status="not_found", plan="", oab="",
            nova=False, message="Licença não encontrada.",
        )

    licenca.last_validated_at = datetime.utcnow()
    await db.commit()
    return LicencaRadarResponse(
        license_key=licenca.license_key, status=licenca.status, plan=licenca.plan,
        oab=(licenca.metadata_ or {}).get("oab", ""), nova=False,
        message="Licença ativa." if licenca.is_valid() else "Licença inativa.",
    )
