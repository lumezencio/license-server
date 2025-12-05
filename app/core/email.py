"""
License Server - Email Service
Serviço de envio de emails para notificações e credenciais
"""
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
import logging

from .config import settings

logger = logging.getLogger(__name__)


class EmailService:
    """Serviço de envio de emails via SMTP"""

    def __init__(self):
        self.host = settings.SMTP_HOST
        self.port = settings.SMTP_PORT
        self.user = settings.SMTP_USER
        self.password = settings.SMTP_PASSWORD
        self.from_email = settings.SMTP_FROM_EMAIL
        self.from_name = settings.SMTP_FROM_NAME
        self.use_tls = settings.SMTP_TLS
        self.use_ssl = settings.SMTP_SSL

    def is_configured(self) -> bool:
        """Verifica se o serviço de email está configurado"""
        return bool(self.user and self.password)

    def send_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None
    ) -> bool:
        """
        Envia um email

        Args:
            to_email: Email do destinatário
            subject: Assunto do email
            html_content: Conteúdo HTML do email
            text_content: Conteúdo texto puro (opcional)

        Returns:
            True se enviado com sucesso, False caso contrário
        """
        if not self.is_configured():
            logger.warning("Email service not configured. Skipping email send.")
            return False

        try:
            # Cria mensagem
            message = MIMEMultipart("alternative")
            message["Subject"] = subject
            message["From"] = f"{self.from_name} <{self.from_email}>"
            message["To"] = to_email

            # Adiciona conteúdo texto
            if text_content:
                part1 = MIMEText(text_content, "plain", "utf-8")
                message.attach(part1)

            # Adiciona conteúdo HTML
            part2 = MIMEText(html_content, "html", "utf-8")
            message.attach(part2)

            # Envia email
            if self.use_ssl:
                context = ssl.create_default_context()
                with smtplib.SMTP_SSL(self.host, self.port, context=context) as server:
                    server.login(self.user, self.password)
                    server.sendmail(self.from_email, to_email, message.as_string())
            else:
                with smtplib.SMTP(self.host, self.port) as server:
                    if self.use_tls:
                        server.starttls()
                    server.login(self.user, self.password)
                    server.sendmail(self.from_email, to_email, message.as_string())

            logger.info(f"Email sent successfully to {to_email}")
            return True

        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {str(e)}")
            return False

    def send_welcome_email(
        self,
        to_email: str,
        name: str,
        license_key: str,
        tenant_code: str,
        password_hint: str,
        trial_days: int,
        login_url: str
    ) -> bool:
        """
        Envia email de boas-vindas com credenciais de acesso

        Args:
            to_email: Email do usuário
            name: Nome do usuário
            license_key: Chave de licença gerada
            tenant_code: Código do tenant (CPF/CNPJ)
            password_hint: Dica da senha inicial
            trial_days: Dias de trial
            login_url: URL de login
        """
        subject = f"Bem-vindo ao Tech-EMP Sistema - Seus dados de acesso"

        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 600px;
            margin: 0 auto;
            padding: 20px;
        }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            text-align: center;
            border-radius: 10px 10px 0 0;
        }}
        .header h1 {{
            margin: 0;
            font-size: 28px;
        }}
        .content {{
            background: #f9fafb;
            padding: 30px;
            border: 1px solid #e5e7eb;
        }}
        .credentials {{
            background: white;
            border: 2px solid #667eea;
            border-radius: 10px;
            padding: 20px;
            margin: 20px 0;
        }}
        .credentials h3 {{
            color: #667eea;
            margin-top: 0;
        }}
        .credential-item {{
            display: flex;
            justify-content: space-between;
            padding: 10px 0;
            border-bottom: 1px solid #e5e7eb;
        }}
        .credential-item:last-child {{
            border-bottom: none;
        }}
        .credential-label {{
            font-weight: bold;
            color: #374151;
        }}
        .credential-value {{
            color: #667eea;
            font-family: monospace;
            font-size: 14px;
        }}
        .license-key {{
            background: #fef3c7;
            border: 1px solid #f59e0b;
            padding: 15px;
            border-radius: 8px;
            text-align: center;
            margin: 20px 0;
        }}
        .license-key code {{
            font-size: 20px;
            font-weight: bold;
            color: #92400e;
            letter-spacing: 2px;
        }}
        .button {{
            display: inline-block;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 15px 30px;
            text-decoration: none;
            border-radius: 8px;
            font-weight: bold;
            margin: 20px 0;
        }}
        .button:hover {{
            opacity: 0.9;
        }}
        .trial-notice {{
            background: #dbeafe;
            border: 1px solid #3b82f6;
            color: #1e40af;
            padding: 15px;
            border-radius: 8px;
            margin: 20px 0;
        }}
        .footer {{
            background: #1f2937;
            color: #9ca3af;
            padding: 20px;
            text-align: center;
            border-radius: 0 0 10px 10px;
            font-size: 12px;
        }}
        .footer a {{
            color: #60a5fa;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Tech-EMP Sistema</h1>
        <p>Sistema de Gestao Empresarial</p>
    </div>

    <div class="content">
        <h2>Ola, {name}!</h2>

        <p>Seja bem-vindo ao <strong>Tech-EMP Sistema</strong>! Seu cadastro foi realizado com sucesso.</p>

        <div class="trial-notice">
            <strong>Periodo de Avaliacao:</strong> Voce tem <strong>{trial_days} dias</strong> para testar todas as funcionalidades do sistema gratuitamente.
        </div>

        <div class="credentials">
            <h3>Seus Dados de Acesso</h3>

            <div class="credential-item">
                <span class="credential-label">E-mail:</span>
                <span class="credential-value">{to_email}</span>
            </div>

            <div class="credential-item">
                <span class="credential-label">Senha inicial:</span>
                <span class="credential-value">{password_hint}</span>
            </div>

            <div class="credential-item">
                <span class="credential-label">Codigo do Tenant:</span>
                <span class="credential-value">{tenant_code}</span>
            </div>
        </div>

        <div class="license-key">
            <p style="margin: 0 0 10px 0; color: #92400e;">Sua Chave de Licenca:</p>
            <code>{license_key}</code>
        </div>

        <p style="text-align: center;">
            <a href="{login_url}" class="button">ACESSAR O SISTEMA</a>
        </p>

        <p><strong>Importante:</strong></p>
        <ul>
            <li>Recomendamos que voce altere sua senha no primeiro acesso</li>
            <li>Guarde sua chave de licenca em local seguro</li>
            <li>Em caso de duvidas, entre em contato com nosso suporte</li>
        </ul>
    </div>

    <div class="footer">
        <p>Este e-mail foi enviado automaticamente pelo sistema Tech-EMP.</p>
        <p>Em caso de duvidas, acesse <a href="{settings.APP_URL}">{settings.APP_URL}</a></p>
        <p>&copy; 2024 Tech-EMP. Todos os direitos reservados.</p>
    </div>
</body>
</html>
"""

        text_content = f"""
Bem-vindo ao Tech-EMP Sistema!

Ola, {name}!

Seu cadastro foi realizado com sucesso.

PERIODO DE AVALIACAO: Voce tem {trial_days} dias para testar gratuitamente.

SEUS DADOS DE ACESSO:
- E-mail: {to_email}
- Senha inicial: {password_hint}
- Codigo do Tenant: {tenant_code}

SUA CHAVE DE LICENCA: {license_key}

ACESSAR O SISTEMA: {login_url}

IMPORTANTE:
- Recomendamos que voce altere sua senha no primeiro acesso
- Guarde sua chave de licenca em local seguro
- Em caso de duvidas, entre em contato com nosso suporte

---
Tech-EMP Sistema
{settings.APP_URL}
"""

        return self.send_email(to_email, subject, html_content, text_content)

    def send_trial_expiring_email(
        self,
        to_email: str,
        name: str,
        days_remaining: int
    ) -> bool:
        """Envia email de aviso de expiracao do trial"""
        subject = f"Seu periodo de avaliacao expira em {days_remaining} dia(s) - Tech-EMP"

        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
</head>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
    <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
        <h2 style="color: #667eea;">Ola, {name}!</h2>

        <p>Seu periodo de avaliacao do <strong>Tech-EMP Sistema</strong> expira em <strong>{days_remaining} dia(s)</strong>.</p>

        <p>Para continuar utilizando o sistema apos esse periodo, escolha um de nossos planos:</p>

        <ul>
            <li><strong>Starter:</strong> Ideal para pequenas empresas</li>
            <li><strong>Professional:</strong> Para empresas em crescimento</li>
            <li><strong>Enterprise:</strong> Solucao completa para grandes operacoes</li>
        </ul>

        <p>Entre em contato conosco para saber mais sobre os planos e precos.</p>

        <p>Atenciosamente,<br>Equipe Tech-EMP</p>
    </div>
</body>
</html>
"""

        return self.send_email(to_email, subject, html_content)


# Instancia global do servico de email
email_service = EmailService()
