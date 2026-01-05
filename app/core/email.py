"""
License Server - Email Service
Serviço de envio de emails para notificações e credenciais
Suporta SMTP e Resend API (para quando SMTP estiver bloqueado)

ANTI-SPAM: Headers e boas práticas implementadas para evitar caixa de spam
"""
import smtplib
import ssl
import httpx
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formatdate, make_msgid
from typing import Optional
import logging
import uuid

from .config import settings

logger = logging.getLogger(__name__)


class EmailService:
    """Serviço de envio de emails via SMTP ou Resend API"""

    def __init__(self):
        self.host = settings.SMTP_HOST
        self.port = settings.SMTP_PORT
        self.user = settings.SMTP_USER
        self.password = settings.SMTP_PASSWORD
        self.from_email = settings.SMTP_FROM_EMAIL
        self.from_name = settings.SMTP_FROM_NAME
        self.use_tls = settings.SMTP_TLS
        self.use_ssl = settings.SMTP_SSL
        self.resend_api_key = settings.RESEND_API_KEY
        self.email_provider = settings.EMAIL_PROVIDER

    def is_configured(self) -> bool:
        """Verifica se o serviço de email está configurado"""
        if self.email_provider == "resend":
            return bool(self.resend_api_key)
        return bool(self.user and self.password)

    def _send_via_resend(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None
    ) -> bool:
        """Envia email via Resend API (HTTP)"""
        try:
            # Usa domínio verificado ou fallback para onboarding@resend.dev
            # Para domínio próprio, verificar em https://resend.com/domains
            from_email = self.from_email
            if not self.from_email.endswith('@resend.dev'):
                # Tenta usar domínio próprio, se falhar usa resend.dev
                from_email = f"Tech-EMP <onboarding@resend.dev>"
            else:
                from_email = f"{self.from_name} <{self.from_email}>"

            response = httpx.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {self.resend_api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "from": from_email,
                    "to": [to_email],
                    "subject": subject,
                    "html": html_content,
                    "text": text_content or "",
                    "reply_to": self.from_email  # Reply vai para o email real
                },
                timeout=30.0
            )

            if response.status_code == 200:
                logger.info(f"Email sent successfully via Resend to {to_email}")
                return True
            else:
                logger.error(f"Resend API error: {response.status_code} - {response.text}")
                return False

        except Exception as e:
            logger.error(f"Failed to send email via Resend to {to_email}: {str(e)}")
            return False

    def _send_via_smtp(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None
    ) -> bool:
        """Envia email via SMTP com headers anti-spam"""
        try:
            # Cria mensagem multipart/alternative (melhor para anti-spam)
            message = MIMEMultipart("alternative")
            message["Subject"] = subject
            message["From"] = f"{self.from_name} <{self.from_email}>"
            message["To"] = to_email

            # === HEADERS ANTI-SPAM ===
            # Message-ID único e bem formatado
            domain = self.from_email.split('@')[1] if '@' in self.from_email else 'tech-emp.com'
            message["Message-ID"] = make_msgid(domain=domain)

            # Data no formato correto RFC 2822
            message["Date"] = formatdate(localtime=True)

            # Reply-To igual ao From (consistência)
            message["Reply-To"] = f"{self.from_name} <{self.from_email}>"

            # MIME-Version (obrigatório)
            message["MIME-Version"] = "1.0"

            # Headers que indicam email legítimo
            message["X-Mailer"] = "Tech-EMP Sistema v1.0"
            message["X-Priority"] = "3"  # Normal priority (1=Alta pode ser spam)
            message["Precedence"] = "bulk"  # Indica email transacional

            # List-Unsubscribe (Gmail e outros verificam isso)
            message["List-Unsubscribe"] = f"<mailto:unsubscribe@tech-emp.com?subject=unsubscribe>"
            message["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"

            # Adiciona conteúdo texto PRIMEIRO (importante para anti-spam)
            # Emails só com HTML são mais propensos a spam
            if text_content:
                part1 = MIMEText(text_content, "plain", "utf-8")
                message.attach(part1)

            # Adiciona conteúdo HTML
            part2 = MIMEText(html_content, "html", "utf-8")
            message.attach(part2)

            # Envia email com timeout de 30 segundos
            if self.use_ssl:
                context = ssl.create_default_context()
                with smtplib.SMTP_SSL(self.host, self.port, context=context, timeout=30) as server:
                    server.login(self.user, self.password)
                    server.sendmail(self.from_email, to_email, message.as_string())
            else:
                with smtplib.SMTP(self.host, self.port, timeout=30) as server:
                    if self.use_tls:
                        server.starttls()
                    server.login(self.user, self.password)
                    server.sendmail(self.from_email, to_email, message.as_string())

            logger.info(f"Email sent successfully via SMTP to {to_email}")
            return True

        except Exception as e:
            logger.error(f"Failed to send email via SMTP to {to_email}: {str(e)}")
            return False

    def send_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None
    ) -> bool:
        """
        Envia um email usando o provedor configurado

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

        # Usa Resend se configurado ou se SMTP falhar
        if self.email_provider == "resend" or self.resend_api_key:
            return self._send_via_resend(to_email, subject, html_content, text_content)

        return self._send_via_smtp(to_email, subject, html_content, text_content)

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
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f1f5f9;">
    <table width="100%" cellpadding="0" cellspacing="0" style="max-width: 650px; margin: 0 auto; background-color: #ffffff;">

        <!-- HEADER -->
        <tr>
            <td style="background: linear-gradient(135deg, #f59e0b 0%, #ea580c 100%); padding: 40px 30px; text-align: center; border-radius: 12px 12px 0 0;">
                <h1 style="margin: 0; color: #ffffff; font-size: 32px; font-weight: bold;">🏆 Tech-EMP</h1>
                <p style="margin: 10px 0 0 0; color: rgba(255,255,255,0.9); font-size: 16px;">Sistema de Gestao Empresarial Completo</p>
            </td>
        </tr>

        <!-- WELCOME MESSAGE -->
        <tr>
            <td style="padding: 40px 30px 20px 30px;">
                <h2 style="margin: 0 0 15px 0; color: #1e293b; font-size: 24px;">Ola, {name}! 👋</h2>
                <p style="margin: 0; color: #475569; font-size: 16px; line-height: 1.6;">
                    E com grande satisfacao que lhe damos as <strong>boas-vindas</strong> ao <strong style="color: #ea580c;">Tech-EMP Sistema</strong>!
                    Seu cadastro foi realizado com sucesso e estamos muito felizes em te-lo conosco.
                </p>
            </td>
        </tr>

        <!-- TRIAL NOTICE -->
        <tr>
            <td style="padding: 0 30px 20px 30px;">
                <table width="100%" cellpadding="0" cellspacing="0" style="background: linear-gradient(135deg, #dbeafe 0%, #e0e7ff 100%); border-radius: 12px; border-left: 4px solid #3b82f6;">
                    <tr>
                        <td style="padding: 20px;">
                            <p style="margin: 0; color: #1e40af; font-size: 16px;">
                                🎁 <strong>Presente Especial:</strong> Voce tem <strong style="color: #1d4ed8; font-size: 18px;">{trial_days} dias GRATIS</strong> para explorar todas as funcionalidades do sistema!
                            </p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>

        <!-- CREDENTIALS BOX -->
        <tr>
            <td style="padding: 0 30px 30px 30px;">
                <table width="100%" cellpadding="0" cellspacing="0" style="background: #ffffff; border: 2px solid #f59e0b; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.05);">
                    <tr>
                        <td style="background: #fef3c7; padding: 15px 20px; border-radius: 10px 10px 0 0;">
                            <h3 style="margin: 0; color: #92400e; font-size: 18px;">🔐 Seus Dados de Acesso</h3>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 20px;">
                            <table width="100%" cellpadding="0" cellspacing="0">
                                <tr>
                                    <td style="padding: 12px 0; border-bottom: 1px solid #e5e7eb;">
                                        <span style="color: #64748b; font-size: 14px;">📧 E-mail:</span><br>
                                        <span style="color: #1e293b; font-size: 16px; font-weight: bold;">{to_email}</span>
                                    </td>
                                </tr>
                                <tr>
                                    <td style="padding: 12px 0; border-bottom: 1px solid #e5e7eb;">
                                        <span style="color: #64748b; font-size: 14px;">🔑 Senha inicial:</span><br>
                                        <span style="color: #ea580c; font-size: 18px; font-weight: bold; font-family: monospace;">{password_hint}</span>
                                    </td>
                                </tr>
                                <tr>
                                    <td style="padding: 12px 0;">
                                        <span style="color: #64748b; font-size: 14px;">🏢 Codigo do Tenant:</span><br>
                                        <span style="color: #1e293b; font-size: 16px; font-weight: bold; font-family: monospace;">{tenant_code}</span>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>

        <!-- LICENSE KEY -->
        <tr>
            <td style="padding: 0 30px 30px 30px;">
                <table width="100%" cellpadding="0" cellspacing="0" style="background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%); border-radius: 12px; border: 1px solid #f59e0b;">
                    <tr>
                        <td style="padding: 20px; text-align: center;">
                            <p style="margin: 0 0 10px 0; color: #92400e; font-size: 14px;">🗝️ Sua Chave de Licenca (guarde em local seguro):</p>
                            <p style="margin: 0; color: #78350f; font-size: 22px; font-weight: bold; font-family: monospace; letter-spacing: 3px;">{license_key}</p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>

        <!-- ACCESS BUTTON -->
        <tr>
            <td style="padding: 0 30px 30px 30px; text-align: center;">
                <a href="{login_url}" style="display: inline-block; background: linear-gradient(135deg, #f59e0b 0%, #ea580c 100%); color: #ffffff; padding: 18px 50px; text-decoration: none; border-radius: 10px; font-weight: bold; font-size: 18px; box-shadow: 0 4px 15px rgba(234, 88, 12, 0.4);">
                    🚀 ACESSAR O SISTEMA
                </a>
            </td>
        </tr>

        <!-- GETTING STARTED SECTION -->
        <tr>
            <td style="padding: 0 30px 30px 30px;">
                <table width="100%" cellpadding="0" cellspacing="0" style="background: #f8fafc; border-radius: 12px; border: 1px solid #e2e8f0;">
                    <tr>
                        <td style="padding: 25px;">
                            <h3 style="margin: 0 0 20px 0; color: #1e293b; font-size: 20px; text-align: center;">
                                📋 Como Comecar - Passo a Passo
                            </h3>
                            <p style="margin: 0 0 20px 0; color: #64748b; font-size: 14px; text-align: center;">
                                Para aproveitar ao maximo o sistema, recomendamos que voce faca os cadastros basicos <strong>antes</strong> de iniciar os lancamentos:
                            </p>

                            <!-- STEP 1 -->
                            <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom: 15px;">
                                <tr>
                                    <td width="50" style="vertical-align: top;">
                                        <div style="background: linear-gradient(135deg, #ec4899 0%, #be185d 100%); color: white; width: 40px; height: 40px; border-radius: 10px; text-align: center; line-height: 40px; font-size: 20px;">👥</div>
                                    </td>
                                    <td style="padding-left: 15px; vertical-align: top;">
                                        <p style="margin: 0; color: #1e293b; font-size: 16px; font-weight: bold;">1. Cadastre seus Clientes</p>
                                        <p style="margin: 5px 0 0 0; color: #64748b; font-size: 14px;">Registre todos os seus clientes com dados completos (nome, CPF/CNPJ, endereco, contato). Isso facilitara as vendas e emissao de notas.</p>
                                    </td>
                                </tr>
                            </table>

                            <!-- STEP 2 -->
                            <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom: 15px;">
                                <tr>
                                    <td width="50" style="vertical-align: top;">
                                        <div style="background: linear-gradient(135deg, #8b5cf6 0%, #6d28d9 100%); color: white; width: 40px; height: 40px; border-radius: 10px; text-align: center; line-height: 40px; font-size: 20px;">📦</div>
                                    </td>
                                    <td style="padding-left: 15px; vertical-align: top;">
                                        <p style="margin: 0; color: #1e293b; font-size: 16px; font-weight: bold;">2. Cadastre seus Produtos</p>
                                        <p style="margin: 5px 0 0 0; color: #64748b; font-size: 14px;">Se voce trabalha com produtos, cadastre-os com codigo, descricao, preco de custo e venda. Assim o controle de estoque sera automatico.</p>
                                    </td>
                                </tr>
                            </table>

                            <!-- STEP 3 -->
                            <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom: 15px;">
                                <tr>
                                    <td width="50" style="vertical-align: top;">
                                        <div style="background: linear-gradient(135deg, #06b6d4 0%, #0891b2 100%); color: white; width: 40px; height: 40px; border-radius: 10px; text-align: center; line-height: 40px; font-size: 20px;">🚚</div>
                                    </td>
                                    <td style="padding-left: 15px; vertical-align: top;">
                                        <p style="margin: 0; color: #1e293b; font-size: 16px; font-weight: bold;">3. Cadastre seus Fornecedores</p>
                                        <p style="margin: 5px 0 0 0; color: #64748b; font-size: 14px;">Registre os fornecedores para facilitar o lancamento de compras e contas a pagar.</p>
                                    </td>
                                </tr>
                            </table>

                            <!-- STEP 4 -->
                            <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom: 15px;">
                                <tr>
                                    <td width="50" style="vertical-align: top;">
                                        <div style="background: linear-gradient(135deg, #10b981 0%, #059669 100%); color: white; width: 40px; height: 40px; border-radius: 10px; text-align: center; line-height: 40px; font-size: 20px;">👤</div>
                                    </td>
                                    <td style="padding-left: 15px; vertical-align: top;">
                                        <p style="margin: 0; color: #1e293b; font-size: 16px; font-weight: bold;">4. Cadastre seus Usuarios</p>
                                        <p style="margin: 5px 0 0 0; color: #64748b; font-size: 14px;">Adicione outros usuarios que irao acessar o sistema, definindo as permissoes de cada um.</p>
                                    </td>
                                </tr>
                            </table>

                            <!-- STEP 5 -->
                            <table width="100%" cellpadding="0" cellspacing="0">
                                <tr>
                                    <td width="50" style="vertical-align: top;">
                                        <div style="background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%); color: white; width: 40px; height: 40px; border-radius: 10px; text-align: center; line-height: 40px; font-size: 20px;">💰</div>
                                    </td>
                                    <td style="padding-left: 15px; vertical-align: top;">
                                        <p style="margin: 0; color: #1e293b; font-size: 16px; font-weight: bold;">5. Inicie os Lancamentos</p>
                                        <p style="margin: 5px 0 0 0; color: #64748b; font-size: 14px;">Apos os cadastros, voce esta pronto! Comece a registrar vendas, compras, contas a pagar e receber.</p>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>

        <!-- MODULES SECTION -->
        <tr>
            <td style="padding: 0 30px 30px 30px;">
                <h3 style="margin: 0 0 20px 0; color: #1e293b; font-size: 18px; text-align: center;">
                    ✨ Modulos Disponiveis no Sistema
                </h3>
                <table width="100%" cellpadding="0" cellspacing="0">
                    <tr>
                        <td width="50%" style="padding: 5px;">
                            <table width="100%" cellpadding="0" cellspacing="0" style="background: #eff6ff; border-radius: 8px; border: 1px solid #bfdbfe;">
                                <tr><td style="padding: 12px; text-align: center;">
                                    <span style="font-size: 24px;">📊</span><br>
                                    <span style="color: #1e40af; font-size: 13px; font-weight: bold;">Dashboard</span>
                                </td></tr>
                            </table>
                        </td>
                        <td width="50%" style="padding: 5px;">
                            <table width="100%" cellpadding="0" cellspacing="0" style="background: #ecfdf5; border-radius: 8px; border: 1px solid #a7f3d0;">
                                <tr><td style="padding: 12px; text-align: center;">
                                    <span style="font-size: 24px;">💵</span><br>
                                    <span style="color: #065f46; font-size: 13px; font-weight: bold;">Financeiro</span>
                                </td></tr>
                            </table>
                        </td>
                    </tr>
                    <tr>
                        <td width="50%" style="padding: 5px;">
                            <table width="100%" cellpadding="0" cellspacing="0" style="background: #fdf4ff; border-radius: 8px; border: 1px solid #f5d0fe;">
                                <tr><td style="padding: 12px; text-align: center;">
                                    <span style="font-size: 24px;">🛒</span><br>
                                    <span style="color: #86198f; font-size: 13px; font-weight: bold;">PDV / Vendas</span>
                                </td></tr>
                            </table>
                        </td>
                        <td width="50%" style="padding: 5px;">
                            <table width="100%" cellpadding="0" cellspacing="0" style="background: #fff7ed; border-radius: 8px; border: 1px solid #fed7aa;">
                                <tr><td style="padding: 12px; text-align: center;">
                                    <span style="font-size: 24px;">📦</span><br>
                                    <span style="color: #c2410c; font-size: 13px; font-weight: bold;">Estoque</span>
                                </td></tr>
                            </table>
                        </td>
                    </tr>
                    <tr>
                        <td width="50%" style="padding: 5px;">
                            <table width="100%" cellpadding="0" cellspacing="0" style="background: #f5f3ff; border-radius: 8px; border: 1px solid #ddd6fe;">
                                <tr><td style="padding: 12px; text-align: center;">
                                    <span style="font-size: 24px;">⚖️</span><br>
                                    <span style="color: #5b21b6; font-size: 13px; font-weight: bold;">Calculos Juridicos</span>
                                </td></tr>
                            </table>
                        </td>
                        <td width="50%" style="padding: 5px;">
                            <table width="100%" cellpadding="0" cellspacing="0" style="background: #fef2f2; border-radius: 8px; border: 1px solid #fecaca;">
                                <tr><td style="padding: 12px; text-align: center;">
                                    <span style="font-size: 24px;">📄</span><br>
                                    <span style="color: #b91c1c; font-size: 13px; font-weight: bold;">Relatorios PDF</span>
                                </td></tr>
                            </table>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>

        <!-- IMPORTANT NOTES -->
        <tr>
            <td style="padding: 0 30px 30px 30px;">
                <table width="100%" cellpadding="0" cellspacing="0" style="background: #fefce8; border-radius: 12px; border: 1px solid #fde047;">
                    <tr>
                        <td style="padding: 20px;">
                            <h4 style="margin: 0 0 15px 0; color: #854d0e; font-size: 16px;">⚠️ Lembretes Importantes:</h4>
                            <ul style="margin: 0; padding-left: 20px; color: #713f12; font-size: 14px; line-height: 1.8;">
                                <li>Recomendamos <strong>alterar sua senha</strong> no primeiro acesso</li>
                                <li>Guarde sua <strong>chave de licenca</strong> em local seguro</li>
                                <li>Faca os cadastros basicos antes de iniciar os lancamentos</li>
                                <li>Explore o Dashboard para ver os indicadores da sua empresa</li>
                            </ul>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>

        <!-- SUPPORT SECTION -->
        <tr>
            <td style="padding: 0 30px 30px 30px;">
                <table width="100%" cellpadding="0" cellspacing="0" style="background: linear-gradient(135deg, #ecfdf5 0%, #d1fae5 100%); border-radius: 12px; border: 1px solid #6ee7b7;">
                    <tr>
                        <td style="padding: 25px; text-align: center;">
                            <h4 style="margin: 0 0 15px 0; color: #065f46; font-size: 18px;">📞 Precisa de Ajuda?</h4>
                            <p style="margin: 0 0 15px 0; color: #047857; font-size: 14px;">
                                Nossa equipe de suporte esta pronta para ajudar voce!
                            </p>
                            <p style="margin: 0; color: #065f46; font-size: 22px; font-weight: bold;">
                                📱 (35) 9.8858-6400
                            </p>
                            <p style="margin: 10px 0 0 0; color: #047857; font-size: 13px;">
                                WhatsApp disponivel • Atendimento rapido e personalizado
                            </p>
                            <p style="margin: 10px 0 0 0; color: #047857; font-size: 13px;">
                                📧 gestao.techemp@gmail.com • Passos - MG
                            </p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>

        <!-- FOOTER -->
        <tr>
            <td style="background: #1e293b; padding: 30px; text-align: center; border-radius: 0 0 12px 12px;">
                <p style="margin: 0 0 10px 0; color: #f59e0b; font-size: 18px; font-weight: bold;">Tech-EMP Sistema</p>
                <p style="margin: 0 0 15px 0; color: #94a3b8; font-size: 13px;">
                    Transformando a gestao da sua empresa
                </p>
                <p style="margin: 0 0 10px 0; color: #64748b; font-size: 12px;">
                    Este e-mail foi enviado automaticamente. Por favor, nao responda.
                </p>
                <p style="margin: 0; color: #64748b; font-size: 12px;">
                    <a href="{settings.APP_URL}" style="color: #60a5fa; text-decoration: none;">{settings.APP_URL}</a>
                </p>
                <p style="margin: 15px 0 0 0; color: #475569; font-size: 11px;">
                    &copy; 2024 Tech-EMP. Todos os direitos reservados.
                </p>
            </td>
        </tr>
    </table>
</body>
</html>
"""

        text_content = f"""
============================================
🎉 BEM-VINDO AO TECH-EMP SISTEMA!
============================================

Ola, {name}!

E com grande satisfacao que lhe damos as boas-vindas ao Tech-EMP Sistema!
Seu cadastro foi realizado com sucesso.

🎁 PRESENTE ESPECIAL: Voce tem {trial_days} dias GRATIS para explorar todas as funcionalidades!

--------------------------------------------
🔐 SEUS DADOS DE ACESSO
--------------------------------------------
📧 E-mail: {to_email}
🔑 Senha inicial: {password_hint}
🏢 Codigo do Tenant: {tenant_code}
🗝️ Chave de Licenca: {license_key}

🚀 ACESSAR O SISTEMA: {login_url}

--------------------------------------------
📋 COMO COMECAR - PASSO A PASSO
--------------------------------------------
Para aproveitar ao maximo o sistema, faca os cadastros basicos ANTES de iniciar os lancamentos:

1. 👥 CADASTRE SEUS CLIENTES
   Registre todos os seus clientes com dados completos (nome, CPF/CNPJ, endereco, contato).

2. 📦 CADASTRE SEUS PRODUTOS
   Se voce trabalha com produtos, cadastre-os com codigo, descricao, preco de custo e venda.

3. 🚚 CADASTRE SEUS FORNECEDORES
   Registre os fornecedores para facilitar o lancamento de compras e contas a pagar.

4. 👤 CADASTRE SEUS USUARIOS
   Adicione outros usuarios que irao acessar o sistema, definindo as permissoes de cada um.

5. 💰 INICIE OS LANCAMENTOS
   Apos os cadastros, comece a registrar vendas, compras, contas a pagar e receber.

--------------------------------------------
✨ MODULOS DISPONIVEIS
--------------------------------------------
📊 Dashboard - Indicadores em tempo real
💵 Financeiro - Contas a pagar e receber
🛒 PDV / Vendas - Ponto de venda rapido
📦 Estoque - Controle de produtos
⚖️ Calculos Juridicos - Correcao monetaria
📄 Relatorios PDF - 13 relatorios completos

--------------------------------------------
⚠️ LEMBRETES IMPORTANTES
--------------------------------------------
• Recomendamos alterar sua senha no primeiro acesso
• Guarde sua chave de licenca em local seguro
• Faca os cadastros basicos antes de iniciar os lancamentos
• Explore o Dashboard para ver os indicadores da sua empresa

--------------------------------------------
📞 PRECISA DE AJUDA?
--------------------------------------------
Nossa equipe de suporte esta pronta para ajudar voce!

📱 WhatsApp: (35) 9.8858-6400
📧 Email: gestao.techemp@gmail.com
📍 Passos - MG
Atendimento rapido e personalizado

--------------------------------------------
Tech-EMP Sistema
{settings.APP_URL}
© 2024 Tech-EMP. Todos os direitos reservados.
"""

        return self.send_email(to_email, subject, html_content, text_content)

    def send_password_reset_email(
        self,
        to_email: str,
        name: str,
        reset_url: str
    ) -> bool:
        """
        Envia email de recuperacao de senha com link seguro.

        Args:
            to_email: Email do usuario
            name: Nome do usuario
            reset_url: URL completa para redefinir senha (com token)
        """
        subject = "Recuperacao de Senha - Tech-EMP Sistema"

        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f1f5f9;">
    <table width="100%" cellpadding="0" cellspacing="0" style="max-width: 600px; margin: 0 auto; background-color: #ffffff;">

        <!-- HEADER -->
        <tr>
            <td style="background: linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%); padding: 40px 30px; text-align: center; border-radius: 12px 12px 0 0;">
                <h1 style="margin: 0; color: #ffffff; font-size: 28px; font-weight: bold;">🔐 Tech-EMP</h1>
                <p style="margin: 10px 0 0 0; color: rgba(255,255,255,0.9); font-size: 16px;">Recuperacao de Senha</p>
            </td>
        </tr>

        <!-- CONTENT -->
        <tr>
            <td style="padding: 40px 30px;">
                <h2 style="margin: 0 0 20px 0; color: #1e293b; font-size: 22px;">Ola, {name}!</h2>
                <p style="margin: 0 0 20px 0; color: #475569; font-size: 16px; line-height: 1.6;">
                    Recebemos uma solicitacao para redefinir a senha da sua conta no <strong style="color: #3b82f6;">Tech-EMP Sistema</strong>.
                </p>
                <p style="margin: 0 0 30px 0; color: #475569; font-size: 16px; line-height: 1.6;">
                    Clique no botao abaixo para criar uma nova senha:
                </p>

                <!-- BUTTON -->
                <div style="text-align: center; margin: 30px 0;">
                    <a href="{reset_url}" style="display: inline-block; background: linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%); color: #ffffff; padding: 16px 40px; text-decoration: none; border-radius: 10px; font-weight: bold; font-size: 16px; box-shadow: 0 4px 15px rgba(59, 130, 246, 0.4);">
                        🔑 REDEFINIR MINHA SENHA
                    </a>
                </div>

                <!-- WARNING BOX -->
                <table width="100%" cellpadding="0" cellspacing="0" style="background: #fef3c7; border-radius: 10px; border: 1px solid #fbbf24; margin: 30px 0;">
                    <tr>
                        <td style="padding: 20px;">
                            <p style="margin: 0 0 10px 0; color: #92400e; font-size: 14px; font-weight: bold;">⚠️ Importante:</p>
                            <ul style="margin: 0; padding-left: 20px; color: #78350f; font-size: 14px; line-height: 1.8;">
                                <li>Este link expira em <strong>1 hora</strong></li>
                                <li>Se voce nao solicitou esta recuperacao, ignore este email</li>
                                <li>Sua senha atual permanece inalterada ate voce criar uma nova</li>
                            </ul>
                        </td>
                    </tr>
                </table>

                <!-- ALTERNATIVE LINK -->
                <p style="margin: 20px 0 0 0; color: #64748b; font-size: 13px; line-height: 1.6;">
                    Se o botao nao funcionar, copie e cole este link no seu navegador:
                </p>
                <p style="margin: 10px 0 0 0; word-break: break-all; background: #f1f5f9; padding: 12px; border-radius: 8px; font-size: 12px; color: #3b82f6;">
                    {reset_url}
                </p>
            </td>
        </tr>

        <!-- SECURITY TIP -->
        <tr>
            <td style="padding: 0 30px 30px 30px;">
                <table width="100%" cellpadding="0" cellspacing="0" style="background: linear-gradient(135deg, #ecfdf5 0%, #d1fae5 100%); border-radius: 10px; border: 1px solid #6ee7b7;">
                    <tr>
                        <td style="padding: 20px;">
                            <p style="margin: 0 0 10px 0; color: #065f46; font-size: 14px; font-weight: bold;">🛡️ Dica de Seguranca</p>
                            <p style="margin: 0; color: #047857; font-size: 13px; line-height: 1.6;">
                                Escolha uma senha forte com pelo menos 8 caracteres, incluindo letras maiusculas, minusculas, numeros e simbolos.
                            </p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>

        <!-- SUPPORT -->
        <tr>
            <td style="padding: 0 30px 30px 30px; text-align: center;">
                <p style="margin: 0; color: #64748b; font-size: 14px;">
                    Precisa de ajuda? Entre em contato conosco:
                </p>
                <p style="margin: 10px 0 0 0; color: #1e293b; font-size: 18px; font-weight: bold;">
                    📱 (35) 9.8858-6400
                </p>
                <p style="margin: 5px 0 0 0; color: #64748b; font-size: 13px;">
                    📧 gestao.techemp@gmail.com • Passos - MG
                </p>
            </td>
        </tr>

        <!-- FOOTER -->
        <tr>
            <td style="background: #1e293b; padding: 25px; text-align: center; border-radius: 0 0 12px 12px;">
                <p style="margin: 0 0 10px 0; color: #3b82f6; font-size: 16px; font-weight: bold;">Tech-EMP Sistema</p>
                <p style="margin: 0 0 10px 0; color: #64748b; font-size: 12px;">
                    Este e-mail foi enviado automaticamente. Por favor, nao responda.
                </p>
                <p style="margin: 0; color: #475569; font-size: 11px;">
                    &copy; 2024 Tech-EMP. Todos os direitos reservados.
                </p>
            </td>
        </tr>
    </table>
</body>
</html>
"""

        text_content = f"""
============================================
🔐 RECUPERACAO DE SENHA - TECH-EMP
============================================

Ola, {name}!

Recebemos uma solicitacao para redefinir a senha da sua conta no Tech-EMP Sistema.

Para criar uma nova senha, acesse o link abaixo:

{reset_url}

--------------------------------------------
⚠️ IMPORTANTE:
--------------------------------------------
• Este link expira em 1 hora
• Se voce nao solicitou esta recuperacao, ignore este email
• Sua senha atual permanece inalterada ate voce criar uma nova

--------------------------------------------
🛡️ DICA DE SEGURANCA:
--------------------------------------------
Escolha uma senha forte com pelo menos 8 caracteres, incluindo letras maiusculas, minusculas, numeros e simbolos.

--------------------------------------------
📞 PRECISA DE AJUDA?
--------------------------------------------
📱 WhatsApp: (35) 9.8858-6400
📧 Email: gestao.techemp@gmail.com
📍 Passos - MG

--------------------------------------------
Tech-EMP Sistema
© 2024 Tech-EMP. Todos os direitos reservados.
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
