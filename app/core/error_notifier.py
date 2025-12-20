"""
License Server - Error Notification System
Envia emails quando erros criticos ocorrem no sistema
"""
import logging
import traceback
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Optional
import asyncio
from functools import wraps

from app.core.config import settings

logger = logging.getLogger(__name__)

# Cache para evitar spam de emails (mesmo erro em sequencia)
_error_cache = {}
_CACHE_TTL_SECONDS = 300  # 5 minutos entre emails do mesmo erro


def _get_error_key(error_type: str, error_msg: str) -> str:
    """Gera chave unica para o erro"""
    return f"{error_type}:{error_msg[:100]}"


def _should_send_notification(error_key: str) -> bool:
    """Verifica se deve enviar notificacao (evita spam)"""
    now = datetime.utcnow()

    if error_key in _error_cache:
        last_sent = _error_cache[error_key]
        if (now - last_sent).total_seconds() < _CACHE_TTL_SECONDS:
            return False

    _error_cache[error_key] = now
    return True


def send_error_notification(
    error_type: str,
    error_message: str,
    error_details: Optional[str] = None,
    tenant_code: Optional[str] = None,
    user_email: Optional[str] = None,
    endpoint: Optional[str] = None,
    request_data: Optional[dict] = None
):
    """
    Envia email de notificacao de erro.

    Args:
        error_type: Tipo do erro (ex: "API_ERROR", "DB_ERROR", "PROVISION_ERROR")
        error_message: Mensagem resumida do erro
        error_details: Stack trace ou detalhes tecnicos
        tenant_code: Codigo do tenant afetado (se aplicavel)
        user_email: Email do usuario que causou o erro (se aplicavel)
        endpoint: Endpoint que gerou o erro
        request_data: Dados da requisicao (sanitizados)
    """
    if not settings.ERROR_NOTIFICATION_ENABLED:
        return

    if not settings.SMTP_USER or not settings.SMTP_PASSWORD:
        logger.warning("SMTP nao configurado - notificacao de erro nao enviada")
        return

    # Verifica cache para evitar spam
    error_key = _get_error_key(error_type, error_message)
    if not _should_send_notification(error_key):
        logger.debug(f"Notificacao de erro suprimida (spam protection): {error_key}")
        return

    try:
        # Monta o email
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"[TECH-EMP ERRO] {error_type}: {error_message[:50]}"
        msg['From'] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>"
        msg['To'] = settings.ERROR_NOTIFICATION_EMAIL

        # Corpo do email em HTML
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; background: #f5f5f5; padding: 20px; }}
                .container {{ max-width: 600px; margin: 0 auto; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
                .header {{ background: linear-gradient(135deg, #dc2626 0%, #991b1b 100%); color: white; padding: 20px; }}
                .header h1 {{ margin: 0; font-size: 20px; }}
                .content {{ padding: 20px; }}
                .field {{ margin-bottom: 15px; }}
                .field-label {{ font-weight: bold; color: #374151; font-size: 12px; text-transform: uppercase; margin-bottom: 5px; }}
                .field-value {{ background: #f9fafb; padding: 10px; border-radius: 4px; border: 1px solid #e5e7eb; font-family: monospace; font-size: 13px; word-break: break-all; }}
                .error-details {{ background: #fef2f2; border: 1px solid #fecaca; color: #991b1b; }}
                .footer {{ background: #f9fafb; padding: 15px 20px; font-size: 11px; color: #6b7280; border-top: 1px solid #e5e7eb; }}
                .badge {{ display: inline-block; padding: 4px 8px; border-radius: 4px; font-size: 11px; font-weight: bold; }}
                .badge-error {{ background: #fef2f2; color: #dc2626; }}
                .badge-info {{ background: #eff6ff; color: #2563eb; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>&#9888; Erro no Sistema Tech-EMP</h1>
                </div>
                <div class="content">
                    <div class="field">
                        <div class="field-label">Tipo do Erro</div>
                        <div class="field-value">
                            <span class="badge badge-error">{error_type}</span>
                        </div>
                    </div>

                    <div class="field">
                        <div class="field-label">Mensagem</div>
                        <div class="field-value">{error_message}</div>
                    </div>

                    <div class="field">
                        <div class="field-label">Data/Hora</div>
                        <div class="field-value">{timestamp}</div>
                    </div>
        """

        if tenant_code:
            html_body += f"""
                    <div class="field">
                        <div class="field-label">Tenant</div>
                        <div class="field-value"><span class="badge badge-info">{tenant_code}</span></div>
                    </div>
            """

        if user_email:
            html_body += f"""
                    <div class="field">
                        <div class="field-label">Usuario</div>
                        <div class="field-value">{user_email}</div>
                    </div>
            """

        if endpoint:
            html_body += f"""
                    <div class="field">
                        <div class="field-label">Endpoint</div>
                        <div class="field-value">{endpoint}</div>
                    </div>
            """

        if request_data:
            # Sanitiza dados sensiveis
            sanitized = {k: '***' if 'password' in k.lower() or 'token' in k.lower() else v
                        for k, v in request_data.items()}
            html_body += f"""
                    <div class="field">
                        <div class="field-label">Dados da Requisicao</div>
                        <div class="field-value"><pre>{str(sanitized)[:500]}</pre></div>
                    </div>
            """

        if error_details:
            html_body += f"""
                    <div class="field">
                        <div class="field-label">Detalhes Tecnicos</div>
                        <div class="field-value error-details"><pre>{error_details[:2000]}</pre></div>
                    </div>
            """

        html_body += """
                </div>
                <div class="footer">
                    Este email foi enviado automaticamente pelo sistema de monitoramento Tech-EMP.<br>
                    Acesse o servidor para verificar os logs completos.
                </div>
            </div>
        </body>
        </html>
        """

        msg.attach(MIMEText(html_body, 'html'))

        # Envia o email
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            if settings.SMTP_TLS:
                server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.send_message(msg)

        logger.info(f"Notificacao de erro enviada: {error_type}")

    except Exception as e:
        logger.error(f"Falha ao enviar notificacao de erro: {e}")


def notify_on_error(error_type: str = "API_ERROR", endpoint: str = None):
    """
    Decorator para notificar erros automaticamente em funcoes async.

    Uso:
        @notify_on_error("CALCULATION_ERROR", "/api/gateway/legal-calculations")
        async def calculate_legal(...):
            ...
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                # Extrai informacoes do contexto
                tenant_code = kwargs.get('tenant_code') or kwargs.get('tenant', {}).get('tenant_code')
                user_email = kwargs.get('user_email') or kwargs.get('user', {}).get('email')

                # Envia notificacao
                send_error_notification(
                    error_type=error_type,
                    error_message=str(e),
                    error_details=traceback.format_exc(),
                    tenant_code=tenant_code,
                    user_email=user_email,
                    endpoint=endpoint or func.__name__
                )

                # Re-raise a excecao
                raise
        return wrapper
    return decorator


def notify_error_sync(
    error_type: str,
    error_message: str,
    error_details: Optional[str] = None,
    **kwargs
):
    """
    Versao sincrona para uso em contextos nao-async.
    Executa em thread separada para nao bloquear.
    """
    import threading

    def _send():
        send_error_notification(
            error_type=error_type,
            error_message=error_message,
            error_details=error_details,
            **kwargs
        )

    thread = threading.Thread(target=_send, daemon=True)
    thread.start()
