"""Dependências de segurança da API.

Contexto: a API original não tinha autenticação nenhuma — upload, listagem e, pior,
`DELETE /documents` (que limpa toda a base vetorial) e `/chat` (que consome créditos do provedor)
estavam abertos para qualquer um que alcançasse a porta.

Aqui entra uma checagem simples por chave de API no header `X-API-Key`, suficiente para o
modelo de implantação deste projeto (serviço único, consumido pelo próprio frontend). Não é um
esquema de identidade de usuário: é controle de acesso ao serviço.
"""

import hmac
from typing import Optional

from fastapi import Header, HTTPException, status

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


async def require_api_key(
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
) -> None:
    """Valida o header `X-API-Key` quando a exigência está ligada nas configurações.

    - `REQUIRE_API_KEY=True` + `API_KEY` definida  -> exige a chave correta.
    - `REQUIRE_API_KEY=True` + `API_KEY` vazia     -> recusa tudo com 503 e orienta a configurar
      (falha fechada: é melhor indisponível do que aberto).
    - `REQUIRE_API_KEY=False`                      -> libera, com aviso no log (uso local).
    """
    if not settings.REQUIRE_API_KEY:
        logger.warning(
            "REQUIRE_API_KEY está desligado: a API está aberta. Use apenas em ambiente local."
        )
        return

    if not settings.API_KEY.strip():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "A API exige autenticação, mas API_KEY não está configurada. "
                "Defina API_KEY no .env ou use REQUIRE_API_KEY=false em ambiente local."
            ),
        )

    if not x_api_key or not hmac.compare_digest(x_api_key, settings.API_KEY):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Chave de API ausente ou inválida (header X-API-Key).",
            headers={"WWW-Authenticate": "X-API-Key"},
        )
