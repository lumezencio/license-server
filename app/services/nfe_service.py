"""
Servico de Emissao de NF-e (Nota Fiscal Eletronica)

Este modulo implementa a comunicacao com os web services da SEFAZ
para emissao, consulta, cancelamento e inutilizacao de NF-e.

Utiliza as bibliotecas:
- lxml: Manipulacao de XML
- signxml: Assinatura digital XML
- zeep: Cliente SOAP para web services
- cryptography: Manipulacao de certificados digitais

Documentacao SEFAZ: https://www.nfe.fazenda.gov.br/portal/principal.aspx
"""

import logging
import hashlib
import base64
import tempfile
import os
import ssl
import io
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Tuple
from decimal import Decimal
from lxml import etree
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, NoEncryption
from cryptography.hazmat.backends import default_backend
from cryptography import x509
from cryptography.fernet import Fernet
from signxml import XMLSigner, XMLVerifier
from signxml.algorithms import SignatureMethod, DigestAlgorithm
import zeep
from zeep.transports import Transport
from zeep.wsse.signature import Signature
import requests
from requests.adapters import HTTPAdapter
import asyncpg
import uuid

logger = logging.getLogger(__name__)

# =====================================================
# URLS DOS WEB SERVICES SEFAZ POR UF
# =====================================================

# URLs de Homologacao (testes)
SEFAZ_URLS_HOMOLOGACAO = {
    # Autorizadores proprios
    'AM': {
        'NfeAutorizacao': 'https://homnfe.sefaz.am.gov.br/services2/services/NfeAutorizacao4',
        'NfeRetAutorizacao': 'https://homnfe.sefaz.am.gov.br/services2/services/NfeRetAutorizacao4',
        'NfeConsultaProtocolo': 'https://homnfe.sefaz.am.gov.br/services2/services/NfeConsulta4',
        'NfeStatusServico': 'https://homnfe.sefaz.am.gov.br/services2/services/NfeStatusServico4',
        'RecepcaoEvento': 'https://homnfe.sefaz.am.gov.br/services2/services/RecepcaoEvento4',
        'NfeInutilizacao': 'https://homnfe.sefaz.am.gov.br/services2/services/NfeInutilizacao4',
    },
    'BA': {
        'NfeAutorizacao': 'https://hnfe.sefaz.ba.gov.br/webservices/NFeAutorizacao4/NFeAutorizacao4.asmx',
        'NfeRetAutorizacao': 'https://hnfe.sefaz.ba.gov.br/webservices/NFeRetAutorizacao4/NFeRetAutorizacao4.asmx',
        'NfeConsultaProtocolo': 'https://hnfe.sefaz.ba.gov.br/webservices/NFeConsultaProtocolo4/NFeConsultaProtocolo4.asmx',
        'NfeStatusServico': 'https://hnfe.sefaz.ba.gov.br/webservices/NFeStatusServico4/NFeStatusServico4.asmx',
        'RecepcaoEvento': 'https://hnfe.sefaz.ba.gov.br/webservices/NFeRecepcaoEvento4/NFeRecepcaoEvento4.asmx',
        'NfeInutilizacao': 'https://hnfe.sefaz.ba.gov.br/webservices/NFeInutilizacao4/NFeInutilizacao4.asmx',
    },
    'GO': {
        'NfeAutorizacao': 'https://homolog.sefaz.go.gov.br/nfe/services/NFeAutorizacao4',
        'NfeRetAutorizacao': 'https://homolog.sefaz.go.gov.br/nfe/services/NFeRetAutorizacao4',
        'NfeConsultaProtocolo': 'https://homolog.sefaz.go.gov.br/nfe/services/NFeConsultaProtocolo4',
        'NfeStatusServico': 'https://homolog.sefaz.go.gov.br/nfe/services/NFeStatusServico4',
        'RecepcaoEvento': 'https://homolog.sefaz.go.gov.br/nfe/services/NFeRecepcaoEvento4',
        'NfeInutilizacao': 'https://homolog.sefaz.go.gov.br/nfe/services/NFeInutilizacao4',
    },
    'MG': {
        'NfeAutorizacao': 'https://hnfe.fazenda.mg.gov.br/nfe2/services/NFeAutorizacao4',
        'NfeRetAutorizacao': 'https://hnfe.fazenda.mg.gov.br/nfe2/services/NFeRetAutorizacao4',
        'NfeConsultaProtocolo': 'https://hnfe.fazenda.mg.gov.br/nfe2/services/NFeConsulta4',
        'NfeStatusServico': 'https://hnfe.fazenda.mg.gov.br/nfe2/services/NFeStatusServico4',
        'RecepcaoEvento': 'https://hnfe.fazenda.mg.gov.br/nfe2/services/NFeRecepcaoEvento4',
        'NfeInutilizacao': 'https://hnfe.fazenda.mg.gov.br/nfe2/services/NFeInutilizacao4',
    },
    'MS': {
        'NfeAutorizacao': 'https://hom.nfe.sefaz.ms.gov.br/ws/NFeAutorizacao4',
        'NfeRetAutorizacao': 'https://hom.nfe.sefaz.ms.gov.br/ws/NFeRetAutorizacao4',
        'NfeConsultaProtocolo': 'https://hom.nfe.sefaz.ms.gov.br/ws/NFeConsultaProtocolo4',
        'NfeStatusServico': 'https://hom.nfe.sefaz.ms.gov.br/ws/NFeStatusServico4',
        'RecepcaoEvento': 'https://hom.nfe.sefaz.ms.gov.br/ws/NFeRecepcaoEvento4',
        'NfeInutilizacao': 'https://hom.nfe.sefaz.ms.gov.br/ws/NFeInutilizacao4',
    },
    'MT': {
        'NfeAutorizacao': 'https://homologacao.sefaz.mt.gov.br/nfews/v2/services/NfeAutorizacao4',
        'NfeRetAutorizacao': 'https://homologacao.sefaz.mt.gov.br/nfews/v2/services/NfeRetAutorizacao4',
        'NfeConsultaProtocolo': 'https://homologacao.sefaz.mt.gov.br/nfews/v2/services/NfeConsulta4',
        'NfeStatusServico': 'https://homologacao.sefaz.mt.gov.br/nfews/v2/services/NfeStatusServico4',
        'RecepcaoEvento': 'https://homologacao.sefaz.mt.gov.br/nfews/v2/services/RecepcaoEvento4',
        'NfeInutilizacao': 'https://homologacao.sefaz.mt.gov.br/nfews/v2/services/NfeInutilizacao4',
    },
    'PE': {
        'NfeAutorizacao': 'https://nfehomolog.sefaz.pe.gov.br/nfe-service/services/NFeAutorizacao4',
        'NfeRetAutorizacao': 'https://nfehomolog.sefaz.pe.gov.br/nfe-service/services/NFeRetAutorizacao4',
        'NfeConsultaProtocolo': 'https://nfehomolog.sefaz.pe.gov.br/nfe-service/services/NFeConsultaProtocolo4',
        'NfeStatusServico': 'https://nfehomolog.sefaz.pe.gov.br/nfe-service/services/NFeStatusServico4',
        'RecepcaoEvento': 'https://nfehomolog.sefaz.pe.gov.br/nfe-service/services/NFeRecepcaoEvento4',
        'NfeInutilizacao': 'https://nfehomolog.sefaz.pe.gov.br/nfe-service/services/NFeInutilizacao4',
    },
    'PR': {
        'NfeAutorizacao': 'https://homologacao.nfe.sefa.pr.gov.br/nfe/NFeAutorizacao4',
        'NfeRetAutorizacao': 'https://homologacao.nfe.sefa.pr.gov.br/nfe/NFeRetAutorizacao4',
        'NfeConsultaProtocolo': 'https://homologacao.nfe.sefa.pr.gov.br/nfe/NFeConsultaProtocolo4',
        'NfeStatusServico': 'https://homologacao.nfe.sefa.pr.gov.br/nfe/NFeStatusServico4',
        'RecepcaoEvento': 'https://homologacao.nfe.sefa.pr.gov.br/nfe/NFeRecepcaoEvento4',
        'NfeInutilizacao': 'https://homologacao.nfe.sefa.pr.gov.br/nfe/NFeInutilizacao4',
    },
    'RS': {
        'NfeAutorizacao': 'https://nfe-homologacao.sefazrs.rs.gov.br/ws/NfeAutorizacao/NFeAutorizacao4.asmx',
        'NfeRetAutorizacao': 'https://nfe-homologacao.sefazrs.rs.gov.br/ws/NfeRetAutorizacao/NFeRetAutorizacao4.asmx',
        'NfeConsultaProtocolo': 'https://nfe-homologacao.sefazrs.rs.gov.br/ws/NfeConsulta/NfeConsulta4.asmx',
        'NfeStatusServico': 'https://nfe-homologacao.sefazrs.rs.gov.br/ws/NfeStatusServico/NfeStatusServico4.asmx',
        'RecepcaoEvento': 'https://nfe-homologacao.sefazrs.rs.gov.br/ws/recepcaoevento/recepcaoevento4.asmx',
        'NfeInutilizacao': 'https://nfe-homologacao.sefazrs.rs.gov.br/ws/nfeinutilizacao/nfeinutilizacao4.asmx',
    },
    'SP': {
        'NfeAutorizacao': 'https://homologacao.nfe.fazenda.sp.gov.br/ws/nfeautorizacao4.asmx',
        'NfeRetAutorizacao': 'https://homologacao.nfe.fazenda.sp.gov.br/ws/nferetautorizacao4.asmx',
        'NfeConsultaProtocolo': 'https://homologacao.nfe.fazenda.sp.gov.br/ws/nfeconsultaprotocolo4.asmx',
        'NfeStatusServico': 'https://homologacao.nfe.fazenda.sp.gov.br/ws/nfestatusservico4.asmx',
        'RecepcaoEvento': 'https://homologacao.nfe.fazenda.sp.gov.br/ws/nferecepcaoevento4.asmx',
        'NfeInutilizacao': 'https://homologacao.nfe.fazenda.sp.gov.br/ws/nfeinutilizacao4.asmx',
    },
    # SVRS - Estados que usam SEFAZ Virtual RS
    'SVRS': {
        'NfeAutorizacao': 'https://nfe-homologacao.svrs.rs.gov.br/ws/NfeAutorizacao/NFeAutorizacao4.asmx',
        'NfeRetAutorizacao': 'https://nfe-homologacao.svrs.rs.gov.br/ws/NfeRetAutorizacao/NFeRetAutorizacao4.asmx',
        'NfeConsultaProtocolo': 'https://nfe-homologacao.svrs.rs.gov.br/ws/NfeConsulta/NfeConsulta4.asmx',
        'NfeStatusServico': 'https://nfe-homologacao.svrs.rs.gov.br/ws/NfeStatusServico/NfeStatusServico4.asmx',
        'RecepcaoEvento': 'https://nfe-homologacao.svrs.rs.gov.br/ws/recepcaoevento/recepcaoevento4.asmx',
        'NfeInutilizacao': 'https://nfe-homologacao.svrs.rs.gov.br/ws/nfeinutilizacao/nfeinutilizacao4.asmx',
    },
}

# Estados que usam SVRS (SEFAZ Virtual RS)
UF_SVRS = ['AC', 'AL', 'AP', 'DF', 'ES', 'PB', 'PI', 'RJ', 'RN', 'RO', 'RR', 'SC', 'SE', 'TO']

# Codigo UF IBGE
CODIGO_UF = {
    'AC': '12', 'AL': '27', 'AP': '16', 'AM': '13', 'BA': '29', 'CE': '23',
    'DF': '53', 'ES': '32', 'GO': '52', 'MA': '21', 'MT': '51', 'MS': '50',
    'MG': '31', 'PA': '15', 'PB': '25', 'PR': '41', 'PE': '26', 'PI': '22',
    'RJ': '33', 'RN': '24', 'RS': '43', 'RO': '11', 'RR': '14', 'SC': '42',
    'SP': '35', 'SE': '28', 'TO': '17'
}

# Namespace da NF-e 4.0
NFE_NAMESPACE = 'http://www.portalfiscal.inf.br/nfe'
NSMAP = {None: NFE_NAMESPACE}


class NFeService:
    """Servico para emissao e gerenciamento de NF-e"""

    def __init__(self, secret_key: str):
        """
        Inicializa o servico de NF-e.

        Args:
            secret_key: Chave secreta para descriptografar senha do certificado
        """
        self.secret_key = secret_key
        self._certificate = None
        self._private_key = None

    def _decrypt_password(self, encrypted_password: str) -> str:
        """Descriptografa a senha do certificado"""
        key = base64.urlsafe_b64encode(hashlib.sha256(self.secret_key.encode()).digest())
        fernet = Fernet(key)
        return fernet.decrypt(encrypted_password.encode()).decode()

    def load_certificate(self, cert_data: bytes, encrypted_password: str) -> Tuple[Any, Any]:
        """
        Carrega o certificado digital A1.

        Args:
            cert_data: Bytes do arquivo .pfx
            encrypted_password: Senha criptografada

        Returns:
            Tupla (private_key, certificate)
        """
        password = self._decrypt_password(encrypted_password)
        private_key, certificate, chain = pkcs12.load_key_and_certificates(
            cert_data, password.encode(), default_backend()
        )
        self._private_key = private_key
        self._certificate = certificate
        return private_key, certificate

    def get_sefaz_url(self, uf: str, servico: str, ambiente: int = 2) -> str:
        """
        Retorna a URL do web service SEFAZ para o estado e servico.

        Args:
            uf: Sigla do estado (ex: 'SP', 'RJ')
            servico: Nome do servico (ex: 'NfeAutorizacao', 'NfeStatusServico')
            ambiente: 1=Producao, 2=Homologacao

        Returns:
            URL do web service
        """
        # Por enquanto so temos URLs de homologacao
        if ambiente == 1:
            # TODO: Adicionar URLs de producao
            raise NotImplementedError("URLs de producao ainda nao implementadas")

        # Verifica se UF usa SVRS
        if uf in UF_SVRS:
            urls = SEFAZ_URLS_HOMOLOGACAO.get('SVRS', {})
        else:
            urls = SEFAZ_URLS_HOMOLOGACAO.get(uf, SEFAZ_URLS_HOMOLOGACAO.get('SVRS', {}))

        return urls.get(servico, '')

    def gerar_chave_acesso(
        self,
        uf: str,
        data_emissao: datetime,
        cnpj: str,
        modelo: int,
        serie: int,
        numero: int,
        tipo_emissao: int = 1,
        codigo_numerico: str = None
    ) -> str:
        """
        Gera a chave de acesso da NF-e (44 digitos).

        Formato: cUF + AAMM + CNPJ + mod + serie + nNF + tpEmis + cNF + cDV

        Args:
            uf: Sigla do estado
            data_emissao: Data de emissao
            cnpj: CNPJ do emitente (apenas numeros)
            modelo: Modelo (55=NF-e, 65=NFC-e)
            serie: Serie da nota
            numero: Numero da nota
            tipo_emissao: Tipo de emissao (1=Normal, 9=Contingencia)
            codigo_numerico: Codigo numerico aleatorio (8 digitos)

        Returns:
            Chave de acesso com 44 digitos
        """
        cuf = CODIGO_UF.get(uf, '35')  # Default SP
        aamm = data_emissao.strftime('%y%m')
        cnpj_limpo = cnpj.replace('.', '').replace('/', '').replace('-', '').zfill(14)
        mod = str(modelo).zfill(2)
        ser = str(serie).zfill(3)
        nnf = str(numero).zfill(9)
        tpemis = str(tipo_emissao)

        if codigo_numerico is None:
            import random
            codigo_numerico = str(random.randint(10000000, 99999999))

        cnf = codigo_numerico.zfill(8)

        # Chave sem digito verificador
        chave_sem_dv = f"{cuf}{aamm}{cnpj_limpo}{mod}{ser}{nnf}{tpemis}{cnf}"

        # Calcula digito verificador (modulo 11)
        dv = self._calcular_dv_mod11(chave_sem_dv)

        return f"{chave_sem_dv}{dv}"

    def _calcular_dv_mod11(self, chave: str) -> str:
        """Calcula digito verificador modulo 11"""
        peso = 2
        soma = 0

        for digito in reversed(chave):
            soma += int(digito) * peso
            peso += 1
            if peso > 9:
                peso = 2

        resto = soma % 11
        dv = 11 - resto

        if dv >= 10:
            return '0'
        return str(dv)

    def gerar_xml_nfe(
        self,
        dados_nfe: Dict[str, Any],
        dados_emitente: Dict[str, Any],
        dados_destinatario: Dict[str, Any],
        itens: list,
        chave_acesso: str
    ) -> str:
        """
        Gera o XML da NF-e no formato exigido pela SEFAZ.

        Args:
            dados_nfe: Dados gerais da NF-e (numero, serie, data, etc)
            dados_emitente: Dados do emitente (empresa)
            dados_destinatario: Dados do destinatario (cliente)
            itens: Lista de itens da nota
            chave_acesso: Chave de acesso gerada

        Returns:
            XML da NF-e como string
        """
        # Cria elemento raiz
        nfe = etree.Element('{%s}NFe' % NFE_NAMESPACE, nsmap=NSMAP)

        # infNFe - Informacoes da NF-e
        infNFe = etree.SubElement(nfe, '{%s}infNFe' % NFE_NAMESPACE)
        infNFe.set('versao', '4.00')
        infNFe.set('Id', f'NFe{chave_acesso}')

        # ide - Identificacao da NF-e
        ide = etree.SubElement(infNFe, '{%s}ide' % NFE_NAMESPACE)
        etree.SubElement(ide, '{%s}cUF' % NFE_NAMESPACE).text = dados_nfe['cUF']
        etree.SubElement(ide, '{%s}cNF' % NFE_NAMESPACE).text = dados_nfe['cNF']
        etree.SubElement(ide, '{%s}natOp' % NFE_NAMESPACE).text = dados_nfe.get('natOp', 'VENDA')
        etree.SubElement(ide, '{%s}mod' % NFE_NAMESPACE).text = str(dados_nfe.get('mod', 55))
        etree.SubElement(ide, '{%s}serie' % NFE_NAMESPACE).text = str(dados_nfe['serie'])
        etree.SubElement(ide, '{%s}nNF' % NFE_NAMESPACE).text = str(dados_nfe['nNF'])
        etree.SubElement(ide, '{%s}dhEmi' % NFE_NAMESPACE).text = dados_nfe['dhEmi']
        etree.SubElement(ide, '{%s}tpNF' % NFE_NAMESPACE).text = '1'  # 1=Saida
        etree.SubElement(ide, '{%s}idDest' % NFE_NAMESPACE).text = dados_nfe.get('idDest', '1')
        etree.SubElement(ide, '{%s}cMunFG' % NFE_NAMESPACE).text = dados_nfe['cMunFG']
        etree.SubElement(ide, '{%s}tpImp' % NFE_NAMESPACE).text = '1'  # DANFE retrato
        etree.SubElement(ide, '{%s}tpEmis' % NFE_NAMESPACE).text = str(dados_nfe.get('tpEmis', 1))
        etree.SubElement(ide, '{%s}cDV' % NFE_NAMESPACE).text = chave_acesso[-1]
        etree.SubElement(ide, '{%s}tpAmb' % NFE_NAMESPACE).text = str(dados_nfe['tpAmb'])
        etree.SubElement(ide, '{%s}finNFe' % NFE_NAMESPACE).text = '1'  # NF-e normal
        etree.SubElement(ide, '{%s}indFinal' % NFE_NAMESPACE).text = '1'  # Consumidor final
        etree.SubElement(ide, '{%s}indPres' % NFE_NAMESPACE).text = '1'  # Presencial
        etree.SubElement(ide, '{%s}procEmi' % NFE_NAMESPACE).text = '0'  # Emissao propria
        etree.SubElement(ide, '{%s}verProc' % NFE_NAMESPACE).text = 'Enterprise System 1.0'

        # emit - Emitente
        emit = etree.SubElement(infNFe, '{%s}emit' % NFE_NAMESPACE)
        etree.SubElement(emit, '{%s}CNPJ' % NFE_NAMESPACE).text = dados_emitente['CNPJ']
        etree.SubElement(emit, '{%s}xNome' % NFE_NAMESPACE).text = dados_emitente['xNome'][:60]

        if dados_emitente.get('xFant'):
            etree.SubElement(emit, '{%s}xFant' % NFE_NAMESPACE).text = dados_emitente['xFant'][:60]

        # Endereco do emitente
        enderEmit = etree.SubElement(emit, '{%s}enderEmit' % NFE_NAMESPACE)
        etree.SubElement(enderEmit, '{%s}xLgr' % NFE_NAMESPACE).text = dados_emitente.get('xLgr', '')[:60]
        etree.SubElement(enderEmit, '{%s}nro' % NFE_NAMESPACE).text = dados_emitente.get('nro', 'S/N')[:60]
        if dados_emitente.get('xCpl'):
            etree.SubElement(enderEmit, '{%s}xCpl' % NFE_NAMESPACE).text = dados_emitente['xCpl'][:60]
        etree.SubElement(enderEmit, '{%s}xBairro' % NFE_NAMESPACE).text = dados_emitente.get('xBairro', '')[:60]
        etree.SubElement(enderEmit, '{%s}cMun' % NFE_NAMESPACE).text = dados_emitente.get('cMun', '')
        etree.SubElement(enderEmit, '{%s}xMun' % NFE_NAMESPACE).text = dados_emitente.get('xMun', '')[:60]
        etree.SubElement(enderEmit, '{%s}UF' % NFE_NAMESPACE).text = dados_emitente.get('UF', '')
        etree.SubElement(enderEmit, '{%s}CEP' % NFE_NAMESPACE).text = dados_emitente.get('CEP', '').replace('-', '')
        etree.SubElement(enderEmit, '{%s}cPais' % NFE_NAMESPACE).text = '1058'  # Brasil
        etree.SubElement(enderEmit, '{%s}xPais' % NFE_NAMESPACE).text = 'BRASIL'

        if dados_emitente.get('fone'):
            etree.SubElement(enderEmit, '{%s}fone' % NFE_NAMESPACE).text = dados_emitente['fone'].replace('(', '').replace(')', '').replace('-', '').replace(' ', '')

        etree.SubElement(emit, '{%s}IE' % NFE_NAMESPACE).text = dados_emitente.get('IE', 'ISENTO')
        etree.SubElement(emit, '{%s}CRT' % NFE_NAMESPACE).text = str(dados_emitente.get('CRT', 1))  # Simples Nacional

        # dest - Destinatario
        dest = etree.SubElement(infNFe, '{%s}dest' % NFE_NAMESPACE)

        cpf_cnpj = dados_destinatario.get('CPF') or dados_destinatario.get('CNPJ', '')
        cpf_cnpj_limpo = cpf_cnpj.replace('.', '').replace('/', '').replace('-', '')

        if len(cpf_cnpj_limpo) == 11:
            etree.SubElement(dest, '{%s}CPF' % NFE_NAMESPACE).text = cpf_cnpj_limpo
        elif len(cpf_cnpj_limpo) == 14:
            etree.SubElement(dest, '{%s}CNPJ' % NFE_NAMESPACE).text = cpf_cnpj_limpo

        etree.SubElement(dest, '{%s}xNome' % NFE_NAMESPACE).text = dados_destinatario.get('xNome', 'CONSUMIDOR')[:60]

        # Endereco do destinatario
        if dados_destinatario.get('xLgr'):
            enderDest = etree.SubElement(dest, '{%s}enderDest' % NFE_NAMESPACE)
            etree.SubElement(enderDest, '{%s}xLgr' % NFE_NAMESPACE).text = dados_destinatario.get('xLgr', '')[:60]
            etree.SubElement(enderDest, '{%s}nro' % NFE_NAMESPACE).text = dados_destinatario.get('nro', 'S/N')[:60]
            if dados_destinatario.get('xCpl'):
                etree.SubElement(enderDest, '{%s}xCpl' % NFE_NAMESPACE).text = dados_destinatario['xCpl'][:60]
            etree.SubElement(enderDest, '{%s}xBairro' % NFE_NAMESPACE).text = dados_destinatario.get('xBairro', '')[:60]
            etree.SubElement(enderDest, '{%s}cMun' % NFE_NAMESPACE).text = dados_destinatario.get('cMun', '')
            etree.SubElement(enderDest, '{%s}xMun' % NFE_NAMESPACE).text = dados_destinatario.get('xMun', '')[:60]
            etree.SubElement(enderDest, '{%s}UF' % NFE_NAMESPACE).text = dados_destinatario.get('UF', '')
            etree.SubElement(enderDest, '{%s}CEP' % NFE_NAMESPACE).text = dados_destinatario.get('CEP', '').replace('-', '')
            etree.SubElement(enderDest, '{%s}cPais' % NFE_NAMESPACE).text = '1058'
            etree.SubElement(enderDest, '{%s}xPais' % NFE_NAMESPACE).text = 'BRASIL'

        etree.SubElement(dest, '{%s}indIEDest' % NFE_NAMESPACE).text = '9'  # Nao contribuinte

        # det - Detalhes dos produtos
        for i, item in enumerate(itens, start=1):
            det = etree.SubElement(infNFe, '{%s}det' % NFE_NAMESPACE)
            det.set('nItem', str(i))

            # Produto
            prod = etree.SubElement(det, '{%s}prod' % NFE_NAMESPACE)
            etree.SubElement(prod, '{%s}cProd' % NFE_NAMESPACE).text = item.get('cProd', str(i))[:60]
            etree.SubElement(prod, '{%s}cEAN' % NFE_NAMESPACE).text = item.get('cEAN', 'SEM GTIN')
            etree.SubElement(prod, '{%s}xProd' % NFE_NAMESPACE).text = item.get('xProd', 'PRODUTO')[:120]
            etree.SubElement(prod, '{%s}NCM' % NFE_NAMESPACE).text = item.get('NCM', '00000000')
            etree.SubElement(prod, '{%s}CFOP' % NFE_NAMESPACE).text = item.get('CFOP', '5102')
            etree.SubElement(prod, '{%s}uCom' % NFE_NAMESPACE).text = item.get('uCom', 'UN')[:6]
            etree.SubElement(prod, '{%s}qCom' % NFE_NAMESPACE).text = f"{float(item.get('qCom', 1)):.4f}"
            etree.SubElement(prod, '{%s}vUnCom' % NFE_NAMESPACE).text = f"{float(item.get('vUnCom', 0)):.10f}"
            etree.SubElement(prod, '{%s}vProd' % NFE_NAMESPACE).text = f"{float(item.get('vProd', 0)):.2f}"
            etree.SubElement(prod, '{%s}cEANTrib' % NFE_NAMESPACE).text = item.get('cEANTrib', 'SEM GTIN')
            etree.SubElement(prod, '{%s}uTrib' % NFE_NAMESPACE).text = item.get('uTrib', item.get('uCom', 'UN'))[:6]
            etree.SubElement(prod, '{%s}qTrib' % NFE_NAMESPACE).text = f"{float(item.get('qTrib', item.get('qCom', 1))):.4f}"
            etree.SubElement(prod, '{%s}vUnTrib' % NFE_NAMESPACE).text = f"{float(item.get('vUnTrib', item.get('vUnCom', 0))):.10f}"
            etree.SubElement(prod, '{%s}indTot' % NFE_NAMESPACE).text = '1'  # Compoe total

            # Imposto
            imposto = etree.SubElement(det, '{%s}imposto' % NFE_NAMESPACE)

            # ICMS
            icms = etree.SubElement(imposto, '{%s}ICMS' % NFE_NAMESPACE)
            icms_sn = etree.SubElement(icms, '{%s}ICMSSN102' % NFE_NAMESPACE)  # Simples Nacional
            etree.SubElement(icms_sn, '{%s}orig' % NFE_NAMESPACE).text = item.get('orig', '0')
            etree.SubElement(icms_sn, '{%s}CSOSN' % NFE_NAMESPACE).text = item.get('CSOSN', '102')

            # PIS
            pis = etree.SubElement(imposto, '{%s}PIS' % NFE_NAMESPACE)
            pis_nt = etree.SubElement(pis, '{%s}PISOutr' % NFE_NAMESPACE)
            etree.SubElement(pis_nt, '{%s}CST' % NFE_NAMESPACE).text = item.get('CST_PIS', '99')
            etree.SubElement(pis_nt, '{%s}vBC' % NFE_NAMESPACE).text = '0.00'
            etree.SubElement(pis_nt, '{%s}pPIS' % NFE_NAMESPACE).text = '0.00'
            etree.SubElement(pis_nt, '{%s}vPIS' % NFE_NAMESPACE).text = '0.00'

            # COFINS
            cofins = etree.SubElement(imposto, '{%s}COFINS' % NFE_NAMESPACE)
            cofins_nt = etree.SubElement(cofins, '{%s}COFINSOutr' % NFE_NAMESPACE)
            etree.SubElement(cofins_nt, '{%s}CST' % NFE_NAMESPACE).text = item.get('CST_COFINS', '99')
            etree.SubElement(cofins_nt, '{%s}vBC' % NFE_NAMESPACE).text = '0.00'
            etree.SubElement(cofins_nt, '{%s}pCOFINS' % NFE_NAMESPACE).text = '0.00'
            etree.SubElement(cofins_nt, '{%s}vCOFINS' % NFE_NAMESPACE).text = '0.00'

        # total - Totais da NF-e
        total = etree.SubElement(infNFe, '{%s}total' % NFE_NAMESPACE)
        icms_tot = etree.SubElement(total, '{%s}ICMSTot' % NFE_NAMESPACE)
        etree.SubElement(icms_tot, '{%s}vBC' % NFE_NAMESPACE).text = '0.00'
        etree.SubElement(icms_tot, '{%s}vICMS' % NFE_NAMESPACE).text = '0.00'
        etree.SubElement(icms_tot, '{%s}vICMSDeson' % NFE_NAMESPACE).text = '0.00'
        etree.SubElement(icms_tot, '{%s}vFCPUFDest' % NFE_NAMESPACE).text = '0.00'
        etree.SubElement(icms_tot, '{%s}vICMSUFDest' % NFE_NAMESPACE).text = '0.00'
        etree.SubElement(icms_tot, '{%s}vICMSUFRemet' % NFE_NAMESPACE).text = '0.00'
        etree.SubElement(icms_tot, '{%s}vFCP' % NFE_NAMESPACE).text = '0.00'
        etree.SubElement(icms_tot, '{%s}vBCST' % NFE_NAMESPACE).text = '0.00'
        etree.SubElement(icms_tot, '{%s}vST' % NFE_NAMESPACE).text = '0.00'
        etree.SubElement(icms_tot, '{%s}vFCPST' % NFE_NAMESPACE).text = '0.00'
        etree.SubElement(icms_tot, '{%s}vFCPSTRet' % NFE_NAMESPACE).text = '0.00'
        etree.SubElement(icms_tot, '{%s}vProd' % NFE_NAMESPACE).text = f"{float(dados_nfe.get('vProd', 0)):.2f}"
        etree.SubElement(icms_tot, '{%s}vFrete' % NFE_NAMESPACE).text = f"{float(dados_nfe.get('vFrete', 0)):.2f}"
        etree.SubElement(icms_tot, '{%s}vSeg' % NFE_NAMESPACE).text = '0.00'
        etree.SubElement(icms_tot, '{%s}vDesc' % NFE_NAMESPACE).text = f"{float(dados_nfe.get('vDesc', 0)):.2f}"
        etree.SubElement(icms_tot, '{%s}vII' % NFE_NAMESPACE).text = '0.00'
        etree.SubElement(icms_tot, '{%s}vIPI' % NFE_NAMESPACE).text = '0.00'
        etree.SubElement(icms_tot, '{%s}vIPIDevol' % NFE_NAMESPACE).text = '0.00'
        etree.SubElement(icms_tot, '{%s}vPIS' % NFE_NAMESPACE).text = '0.00'
        etree.SubElement(icms_tot, '{%s}vCOFINS' % NFE_NAMESPACE).text = '0.00'
        etree.SubElement(icms_tot, '{%s}vOutro' % NFE_NAMESPACE).text = '0.00'
        etree.SubElement(icms_tot, '{%s}vNF' % NFE_NAMESPACE).text = f"{float(dados_nfe.get('vNF', 0)):.2f}"

        # transp - Transporte
        transp = etree.SubElement(infNFe, '{%s}transp' % NFE_NAMESPACE)
        etree.SubElement(transp, '{%s}modFrete' % NFE_NAMESPACE).text = '9'  # Sem frete

        # pag - Pagamento
        pag = etree.SubElement(infNFe, '{%s}pag' % NFE_NAMESPACE)
        det_pag = etree.SubElement(pag, '{%s}detPag' % NFE_NAMESPACE)
        etree.SubElement(det_pag, '{%s}tPag' % NFE_NAMESPACE).text = dados_nfe.get('tPag', '01')  # Dinheiro
        etree.SubElement(det_pag, '{%s}vPag' % NFE_NAMESPACE).text = f"{float(dados_nfe.get('vNF', 0)):.2f}"

        # infAdic - Informacoes adicionais
        if dados_nfe.get('infCpl'):
            inf_adic = etree.SubElement(infNFe, '{%s}infAdic' % NFE_NAMESPACE)
            etree.SubElement(inf_adic, '{%s}infCpl' % NFE_NAMESPACE).text = dados_nfe['infCpl'][:5000]

        return etree.tostring(nfe, encoding='unicode', pretty_print=True)

    def assinar_xml(self, xml_str: str) -> str:
        """
        Assina digitalmente o XML da NF-e.

        Args:
            xml_str: XML da NF-e como string

        Returns:
            XML assinado como string
        """
        if not self._private_key or not self._certificate:
            raise ValueError("Certificado digital nao carregado")

        # Parse XML
        xml_doc = etree.fromstring(xml_str.encode('utf-8'))

        # Encontra elemento a ser assinado (infNFe)
        infNFe = xml_doc.find('.//{%s}infNFe' % NFE_NAMESPACE)
        if infNFe is None:
            raise ValueError("Elemento infNFe nao encontrado no XML")

        # Configura assinatura
        signer = XMLSigner(
            method=SignatureMethod.RSA_SHA1,
            digest_algorithm=DigestAlgorithm.SHA1,
            c14n_algorithm='http://www.w3.org/TR/2001/REC-xml-c14n-20010315',
            signature_algorithm='http://www.w3.org/2000/09/xmldsig#rsa-sha1'
        )

        # Assina
        signed_xml = signer.sign(
            xml_doc,
            key=self._private_key,
            cert=self._certificate,
            reference_uri=f"#{infNFe.get('Id')}"
        )

        return etree.tostring(signed_xml, encoding='unicode', pretty_print=True)

    async def consultar_status_servico(self, uf: str, ambiente: int = 2) -> Dict[str, Any]:
        """
        Consulta status do servico SEFAZ.

        Args:
            uf: Sigla do estado
            ambiente: 1=Producao, 2=Homologacao

        Returns:
            Dicionario com status do servico
        """
        url = self.get_sefaz_url(uf, 'NfeStatusServico', ambiente)

        if not url:
            return {
                'cStat': '999',
                'xMotivo': f'URL do servico nao encontrada para UF {uf}',
                'status': 'ERROR'
            }

        try:
            # Cria XML de consulta
            cons_stat = etree.Element('{%s}consStatServ' % NFE_NAMESPACE, nsmap=NSMAP)
            cons_stat.set('versao', '4.00')
            etree.SubElement(cons_stat, '{%s}tpAmb' % NFE_NAMESPACE).text = str(ambiente)
            etree.SubElement(cons_stat, '{%s}cUF' % NFE_NAMESPACE).text = CODIGO_UF.get(uf, '35')
            etree.SubElement(cons_stat, '{%s}xServ' % NFE_NAMESPACE).text = 'STATUS'

            xml_str = etree.tostring(cons_stat, encoding='unicode')

            # TODO: Implementar chamada SOAP com zeep
            # Por enquanto retorna simulacao
            return {
                'cStat': '107',
                'xMotivo': 'Servico em Operacao',
                'status': 'OK',
                'url': url
            }

        except Exception as e:
            logger.error(f"Erro ao consultar status SEFAZ: {e}")
            return {
                'cStat': '999',
                'xMotivo': str(e),
                'status': 'ERROR'
            }


# =====================================================
# FUNCOES AUXILIARES PARA USO NO GATEWAY
# =====================================================

async def processar_emissao_nfe(
    conn: asyncpg.Connection,
    nfe_id: str,
    service: NFeService
) -> Dict[str, Any]:
    """
    Processa a emissao de uma NF-e pendente.

    Args:
        conn: Conexao com banco do tenant
        nfe_id: ID da emissao
        service: Instancia do NFeService

    Returns:
        Resultado do processamento
    """
    try:
        # Busca dados da emissao
        nfe = await conn.fetchrow(
            "SELECT * FROM nfe_emissions WHERE id = $1",
            nfe_id
        )

        if not nfe:
            return {'success': False, 'error': 'Emissao nao encontrada'}

        if nfe['status'] != 'PENDING':
            return {'success': False, 'error': f'Status invalido: {nfe["status"]}'}

        # Busca configuracoes fiscais
        fiscal = await conn.fetchrow(
            "SELECT * FROM fiscal_settings WHERE is_active = TRUE LIMIT 1"
        )

        if not fiscal or not fiscal['is_configured']:
            return {'success': False, 'error': 'Configuracoes fiscais nao encontradas'}

        # Busca dados da venda
        sale = await conn.fetchrow(
            "SELECT * FROM sales WHERE id = $1",
            nfe['sale_id']
        )

        if not sale:
            return {'success': False, 'error': 'Venda nao encontrada'}

        # Busca itens da venda
        items = await conn.fetch(
            "SELECT * FROM sale_items WHERE sale_id = $1",
            sale['id']
        )

        # Busca dados do cliente
        customer = await conn.fetchrow(
            "SELECT * FROM customers WHERE id = $1",
            sale['customer_id']
        )

        # Busca dados da empresa
        company = await conn.fetchrow("SELECT * FROM companies LIMIT 1")

        if not company:
            return {'success': False, 'error': 'Dados da empresa nao cadastrados'}

        # Carrega certificado
        service.load_certificate(
            fiscal['certificate_file'],
            fiscal['certificate_password_encrypted']
        )

        # Gera chave de acesso
        data_emissao = datetime.now(timezone.utc)
        chave_acesso = service.gerar_chave_acesso(
            uf=fiscal['uf'],
            data_emissao=data_emissao,
            cnpj=company['document'],
            modelo=nfe['modelo'],
            serie=nfe['serie'],
            numero=nfe['numero_nfe'],
            tipo_emissao=1
        )

        # Prepara dados para geracao do XML
        dados_nfe = {
            'cUF': CODIGO_UF.get(fiscal['uf'], '35'),
            'cNF': chave_acesso[35:43],
            'natOp': 'VENDA DE MERCADORIA',
            'mod': nfe['modelo'],
            'serie': nfe['serie'],
            'nNF': nfe['numero_nfe'],
            'dhEmi': data_emissao.strftime('%Y-%m-%dT%H:%M:%S-03:00'),
            'tpAmb': fiscal['ambiente'],
            'cMunFG': fiscal['codigo_municipio'] or '3550308',
            'tpEmis': 1,
            'vProd': float(sale['subtotal'] or 0),
            'vDesc': float(sale['discount_amount'] or 0),
            'vFrete': float(sale['shipping_amount'] or 0),
            'vNF': float(sale['total_amount'] or 0),
            'tPag': '01',  # Dinheiro
        }

        dados_emitente = {
            'CNPJ': (company['document'] or '').replace('.', '').replace('/', '').replace('-', ''),
            'xNome': company['legal_name'] or company['trade_name'] or '',
            'xFant': company['trade_name'] or '',
            'xLgr': company['street'] or '',
            'nro': company['number'] or 'S/N',
            'xCpl': company['complement'] or '',
            'xBairro': company['neighborhood'] or '',
            'cMun': fiscal['codigo_municipio'] or '3550308',
            'xMun': company['city'] or '',
            'UF': company['state'] or fiscal['uf'],
            'CEP': (company['zip_code'] or '').replace('-', ''),
            'fone': company['phone'] or '',
            'IE': company['state_registration'] or 'ISENTO',
            'CRT': fiscal['regime_tributario'] or 1,
        }

        dados_destinatario = {}
        if customer:
            cpf_cnpj = (customer['cpf_cnpj'] or '').replace('.', '').replace('/', '').replace('-', '')
            if len(cpf_cnpj) == 11:
                dados_destinatario['CPF'] = cpf_cnpj
            else:
                dados_destinatario['CNPJ'] = cpf_cnpj

            nome = customer['company_name'] or customer['trade_name'] or \
                   f"{customer['first_name'] or ''} {customer['last_name'] or ''}".strip() or 'CONSUMIDOR'
            dados_destinatario['xNome'] = nome
            dados_destinatario['xLgr'] = customer['address'] or ''
            dados_destinatario['nro'] = customer['address_number'] or 'S/N'
            dados_destinatario['xCpl'] = customer['address_complement'] or ''
            dados_destinatario['xBairro'] = customer['neighborhood'] or ''
            dados_destinatario['xMun'] = customer['city'] or ''
            dados_destinatario['UF'] = customer['state'] or ''
            dados_destinatario['CEP'] = (customer['zip_code'] or '').replace('-', '')

        # Prepara itens
        itens_nfe = []
        for item in items:
            itens_nfe.append({
                'cProd': item['product_code'] or str(item['id'])[:60],
                'xProd': item['product_name'] or 'PRODUTO',
                'NCM': item['ncm_code'] or '00000000',
                'CFOP': item['cfop'] or '5102',
                'uCom': item['unit'] or 'UN',
                'qCom': float(item['quantity'] or 1),
                'vUnCom': float(item['unit_price'] or 0),
                'vProd': float(item['total_amount'] or 0),
            })

        # Gera XML
        xml_nfe = service.gerar_xml_nfe(
            dados_nfe=dados_nfe,
            dados_emitente=dados_emitente,
            dados_destinatario=dados_destinatario,
            itens=itens_nfe,
            chave_acesso=chave_acesso
        )

        # Assina XML
        xml_assinado = service.assinar_xml(xml_nfe)

        # Atualiza registro com XML e chave de acesso
        await conn.execute("""
            UPDATE nfe_emissions SET
                chave_acesso = $1,
                xml_nfe = $2,
                tentativas_envio = tentativas_envio + 1,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = $3
        """, chave_acesso, xml_assinado, nfe_id)

        # TODO: Enviar para SEFAZ via web service
        # Por enquanto, simula autorizacao em homologacao
        if fiscal['ambiente'] == 2:  # Homologacao
            protocolo = f"HOM{datetime.now().strftime('%Y%m%d%H%M%S')}"

            await conn.execute("""
                UPDATE nfe_emissions SET
                    status = 'AUTHORIZED',
                    protocolo_autorizacao = $1,
                    data_autorizacao = CURRENT_TIMESTAMP,
                    codigo_retorno = '100',
                    motivo_retorno = 'Autorizado o uso da NF-e (HOMOLOGACAO)',
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = $2
            """, protocolo, nfe_id)

            return {
                'success': True,
                'chave_acesso': chave_acesso,
                'protocolo': protocolo,
                'status': 'AUTHORIZED',
                'message': 'NF-e autorizada em homologacao'
            }
        else:
            # Em producao, precisaria enviar para SEFAZ
            return {
                'success': False,
                'error': 'Emissao em producao requer implementacao completa do web service'
            }

    except Exception as e:
        logger.error(f"Erro ao processar emissao NF-e: {e}")
        import traceback
        traceback.print_exc()

        # Atualiza com erro
        await conn.execute("""
            UPDATE nfe_emissions SET
                status = 'ERROR',
                ultimo_erro = $1,
                tentativas_envio = tentativas_envio + 1,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = $2
        """, str(e), nfe_id)

        return {
            'success': False,
            'error': str(e)
        }


# =====================================================
# CLASSE PARA COMUNICACAO SOAP COM SEFAZ
# =====================================================

class SefazClient:
    """
    Cliente para comunicacao SOAP com web services da SEFAZ.
    Gerencia certificados, sessoes SSL e chamadas aos servicos.
    """

    def __init__(self, cert_data: bytes, cert_password: str):
        """
        Inicializa cliente SEFAZ com certificado.

        Args:
            cert_data: Bytes do arquivo .pfx/.p12
            cert_password: Senha do certificado
        """
        self._cert_data = cert_data
        self._cert_password = cert_password
        self._cert_file = None
        self._key_file = None
        self._session = None
        self._setup_certificate()

    def _setup_certificate(self):
        """Extrai certificado e chave privada para arquivos temporarios."""
        try:
            # Carrega PKCS12
            private_key, certificate, chain = pkcs12.load_key_and_certificates(
                self._cert_data,
                self._cert_password.encode() if self._cert_password else None,
                default_backend()
            )

            # Cria arquivos temporarios para cert e key
            self._cert_file = tempfile.NamedTemporaryFile(
                mode='wb', suffix='.pem', delete=False
            )
            self._key_file = tempfile.NamedTemporaryFile(
                mode='wb', suffix='.pem', delete=False
            )

            # Escreve certificado em PEM
            self._cert_file.write(certificate.public_bytes(Encoding.PEM))
            self._cert_file.flush()

            # Escreve chave privada em PEM
            self._key_file.write(private_key.private_bytes(
                Encoding.PEM,
                PrivateFormat.TraditionalOpenSSL,
                NoEncryption()
            ))
            self._key_file.flush()

            # Cria sessao requests com certificado
            self._session = requests.Session()
            self._session.cert = (self._cert_file.name, self._key_file.name)
            self._session.verify = True

            logger.info("Certificado SEFAZ configurado com sucesso")

        except Exception as e:
            logger.error(f"Erro ao configurar certificado SEFAZ: {e}")
            raise

    def __del__(self):
        """Limpa arquivos temporarios."""
        try:
            if self._cert_file and os.path.exists(self._cert_file.name):
                os.unlink(self._cert_file.name)
            if self._key_file and os.path.exists(self._key_file.name):
                os.unlink(self._key_file.name)
        except:
            pass

    def _criar_envelope_soap(self, xml_content: str) -> str:
        """
        Cria envelope SOAP para envio ao web service.

        Args:
            xml_content: Conteudo XML da requisicao

        Returns:
            Envelope SOAP completo
        """
        envelope = f"""<?xml version="1.0" encoding="UTF-8"?>
<soap12:Envelope xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">
    <soap12:Header/>
    <soap12:Body>
        <nfeDadosMsg xmlns="http://www.portalfiscal.inf.br/nfe/wsdl/NFeAutorizacao4">
            {xml_content}
        </nfeDadosMsg>
    </soap12:Body>
</soap12:Envelope>"""
        return envelope

    def enviar_lote(self, xml_assinado: str, url: str) -> Dict[str, Any]:
        """
        Envia lote de NF-e para autorizacao.

        Args:
            xml_assinado: XML da NF-e assinado
            url: URL do web service NfeAutorizacao

        Returns:
            Dicionario com resposta da SEFAZ
        """
        try:
            # Cria lote de envio
            lote_id = datetime.now().strftime('%Y%m%d%H%M%S')

            # Monta XML do lote
            lote_xml = f"""<enviNFe xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00">
    <idLote>{lote_id}</idLote>
    <indSinc>1</indSinc>
    {xml_assinado}
</enviNFe>"""

            # Cria envelope SOAP
            envelope = self._criar_envelope_soap(lote_xml)

            # Envia requisicao
            headers = {
                'Content-Type': 'application/soap+xml; charset=utf-8',
                'SOAPAction': 'http://www.portalfiscal.inf.br/nfe/wsdl/NFeAutorizacao4/nfeAutorizacaoLote'
            }

            response = self._session.post(
                url,
                data=envelope.encode('utf-8'),
                headers=headers,
                timeout=60
            )

            if response.status_code != 200:
                return {
                    'success': False,
                    'cStat': '999',
                    'xMotivo': f'Erro HTTP: {response.status_code}',
                    'response': response.text[:500]
                }

            # Parse da resposta
            return self._parse_resposta_autorizacao(response.text)

        except requests.exceptions.Timeout:
            return {
                'success': False,
                'cStat': '999',
                'xMotivo': 'Timeout na comunicacao com SEFAZ'
            }
        except requests.exceptions.SSLError as e:
            return {
                'success': False,
                'cStat': '999',
                'xMotivo': f'Erro SSL: {str(e)}'
            }
        except Exception as e:
            logger.error(f"Erro ao enviar lote SEFAZ: {e}")
            return {
                'success': False,
                'cStat': '999',
                'xMotivo': str(e)
            }

    def _parse_resposta_autorizacao(self, xml_response: str) -> Dict[str, Any]:
        """
        Parse da resposta de autorizacao da SEFAZ.

        Args:
            xml_response: XML de resposta

        Returns:
            Dicionario com dados extraidos
        """
        try:
            # Remove declaracao XML se houver
            if '<?xml' in xml_response:
                xml_response = xml_response.split('?>', 1)[1] if '?>' in xml_response else xml_response

            root = etree.fromstring(xml_response.encode('utf-8'))

            # Namespaces
            ns = {
                'soap': 'http://www.w3.org/2003/05/soap-envelope',
                'nfe': 'http://www.portalfiscal.inf.br/nfe'
            }

            # Busca retorno
            ret_env = root.find('.//nfe:retEnviNFe', ns)
            if ret_env is None:
                # Tenta sem namespace
                ret_env = root.find('.//{http://www.portalfiscal.inf.br/nfe}retEnviNFe')

            if ret_env is None:
                return {
                    'success': False,
                    'cStat': '999',
                    'xMotivo': 'Resposta invalida da SEFAZ',
                    'xml_response': xml_response[:1000]
                }

            cStat = ret_env.findtext('.//{http://www.portalfiscal.inf.br/nfe}cStat', '')
            xMotivo = ret_env.findtext('.//{http://www.portalfiscal.inf.br/nfe}xMotivo', '')

            result = {
                'cStat': cStat,
                'xMotivo': xMotivo
            }

            # Verifica se foi autorizado (codigo 104 = lote processado)
            if cStat == '104':
                # Busca protocolo
                prot = ret_env.find('.//{http://www.portalfiscal.inf.br/nfe}protNFe')
                if prot is not None:
                    inf_prot = prot.find('.//{http://www.portalfiscal.inf.br/nfe}infProt')
                    if inf_prot is not None:
                        prot_cStat = inf_prot.findtext('.//{http://www.portalfiscal.inf.br/nfe}cStat', '')
                        prot_xMotivo = inf_prot.findtext('.//{http://www.portalfiscal.inf.br/nfe}xMotivo', '')
                        protocolo = inf_prot.findtext('.//{http://www.portalfiscal.inf.br/nfe}nProt', '')
                        digest = inf_prot.findtext('.//{http://www.portalfiscal.inf.br/nfe}digVal', '')

                        result['prot_cStat'] = prot_cStat
                        result['prot_xMotivo'] = prot_xMotivo
                        result['protocolo'] = protocolo
                        result['digest_value'] = digest

                        # 100 = Autorizado
                        if prot_cStat == '100':
                            result['success'] = True
                            result['status'] = 'AUTHORIZED'
                        else:
                            result['success'] = False
                            result['status'] = 'REJECTED'
            else:
                result['success'] = False
                result['status'] = 'ERROR'

            return result

        except Exception as e:
            logger.error(f"Erro ao fazer parse da resposta SEFAZ: {e}")
            return {
                'success': False,
                'cStat': '999',
                'xMotivo': f'Erro no parse: {str(e)}'
            }

    def consultar_protocolo(self, chave_acesso: str, url: str, ambiente: int = 2) -> Dict[str, Any]:
        """
        Consulta protocolo de NF-e na SEFAZ.

        Args:
            chave_acesso: Chave de acesso da NF-e (44 digitos)
            url: URL do web service NfeConsultaProtocolo
            ambiente: 1=Producao, 2=Homologacao

        Returns:
            Dicionario com dados do protocolo
        """
        try:
            # Monta XML de consulta
            cons_xml = f"""<consSitNFe xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00">
    <tpAmb>{ambiente}</tpAmb>
    <xServ>CONSULTAR</xServ>
    <chNFe>{chave_acesso}</chNFe>
</consSitNFe>"""

            # Cria envelope SOAP
            envelope = f"""<?xml version="1.0" encoding="UTF-8"?>
<soap12:Envelope xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">
    <soap12:Header/>
    <soap12:Body>
        <nfeDadosMsg xmlns="http://www.portalfiscal.inf.br/nfe/wsdl/NFeConsultaProtocolo4">
            {cons_xml}
        </nfeDadosMsg>
    </soap12:Body>
</soap12:Envelope>"""

            headers = {
                'Content-Type': 'application/soap+xml; charset=utf-8',
                'SOAPAction': 'http://www.portalfiscal.inf.br/nfe/wsdl/NFeConsultaProtocolo4/nfeConsultaNF'
            }

            response = self._session.post(
                url,
                data=envelope.encode('utf-8'),
                headers=headers,
                timeout=30
            )

            if response.status_code != 200:
                return {
                    'success': False,
                    'cStat': '999',
                    'xMotivo': f'Erro HTTP: {response.status_code}'
                }

            # Parse simplificado
            root = etree.fromstring(response.text.encode('utf-8'))
            cStat = root.findtext('.//{http://www.portalfiscal.inf.br/nfe}cStat', '')
            xMotivo = root.findtext('.//{http://www.portalfiscal.inf.br/nfe}xMotivo', '')
            protocolo = root.findtext('.//{http://www.portalfiscal.inf.br/nfe}nProt', '')

            return {
                'success': cStat == '100',
                'cStat': cStat,
                'xMotivo': xMotivo,
                'protocolo': protocolo
            }

        except Exception as e:
            logger.error(f"Erro ao consultar protocolo: {e}")
            return {
                'success': False,
                'cStat': '999',
                'xMotivo': str(e)
            }

    def enviar_evento(self, xml_evento: str, url: str) -> Dict[str, Any]:
        """
        Envia evento (cancelamento, carta correcao) para SEFAZ.

        Args:
            xml_evento: XML do evento assinado
            url: URL do web service RecepcaoEvento

        Returns:
            Dicionario com resposta
        """
        try:
            # Cria envelope SOAP
            envelope = f"""<?xml version="1.0" encoding="UTF-8"?>
<soap12:Envelope xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">
    <soap12:Header/>
    <soap12:Body>
        <nfeDadosMsg xmlns="http://www.portalfiscal.inf.br/nfe/wsdl/NFeRecepcaoEvento4">
            {xml_evento}
        </nfeDadosMsg>
    </soap12:Body>
</soap12:Envelope>"""

            headers = {
                'Content-Type': 'application/soap+xml; charset=utf-8',
                'SOAPAction': 'http://www.portalfiscal.inf.br/nfe/wsdl/NFeRecepcaoEvento4/nfeRecepcaoEvento'
            }

            response = self._session.post(
                url,
                data=envelope.encode('utf-8'),
                headers=headers,
                timeout=30
            )

            if response.status_code != 200:
                return {
                    'success': False,
                    'cStat': '999',
                    'xMotivo': f'Erro HTTP: {response.status_code}'
                }

            # Parse da resposta
            root = etree.fromstring(response.text.encode('utf-8'))
            cStat = root.findtext('.//{http://www.portalfiscal.inf.br/nfe}cStat', '')
            xMotivo = root.findtext('.//{http://www.portalfiscal.inf.br/nfe}xMotivo', '')
            protocolo = root.findtext('.//{http://www.portalfiscal.inf.br/nfe}nProt', '')

            # 135 = Evento registrado e vinculado a NF-e
            # 155 = Cancelamento homologado fora de prazo
            success = cStat in ['135', '155']

            return {
                'success': success,
                'cStat': cStat,
                'xMotivo': xMotivo,
                'protocolo': protocolo,
                'xml_response': response.text
            }

        except Exception as e:
            logger.error(f"Erro ao enviar evento: {e}")
            return {
                'success': False,
                'cStat': '999',
                'xMotivo': str(e)
            }


# =====================================================
# GERACAO DE DANFE (PDF)
# =====================================================

class DanfeGenerator:
    """
    Gerador de DANFE (Documento Auxiliar da Nota Fiscal Eletronica).
    Cria PDF seguindo layout oficial da SEFAZ.
    """

    def __init__(self):
        """Inicializa gerador DANFE."""
        # Verifica se reportlab esta disponivel
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.pdfgen import canvas
            from reportlab.lib.units import mm
            from reportlab.lib import colors
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.ttfonts import TTFont
            self._reportlab_available = True
        except ImportError:
            self._reportlab_available = False
            logger.warning("ReportLab nao instalado - DANFE sera gerado como texto")

    def gerar_danfe(self, dados_nfe: Dict[str, Any], xml_nfe: str = None) -> bytes:
        """
        Gera DANFE em formato PDF.

        Args:
            dados_nfe: Dicionario com dados da NF-e
            xml_nfe: XML da NF-e (opcional, para extrair dados)

        Returns:
            Bytes do arquivo PDF
        """
        if self._reportlab_available:
            return self._gerar_danfe_reportlab(dados_nfe)
        else:
            return self._gerar_danfe_simples(dados_nfe)

    def _gerar_danfe_reportlab(self, dados: Dict[str, Any]) -> bytes:
        """Gera DANFE usando ReportLab."""
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
        from reportlab.lib.units import mm
        from reportlab.lib import colors

        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4

        # Margens
        margin = 10 * mm
        x = margin
        y = height - margin

        # === CABECALHO ===
        # Caixa identificacao
        c.setStrokeColor(colors.black)
        c.setLineWidth(0.5)
        c.rect(x, y - 30*mm, width - 2*margin, 30*mm)

        # Titulo
        c.setFont("Helvetica-Bold", 12)
        c.drawString(x + 5*mm, y - 8*mm, "DANFE")
        c.setFont("Helvetica", 8)
        c.drawString(x + 5*mm, y - 13*mm, "Documento Auxiliar da")
        c.drawString(x + 5*mm, y - 17*mm, "Nota Fiscal Eletronica")

        # Numero e serie
        c.setFont("Helvetica-Bold", 10)
        c.drawString(x + 45*mm, y - 8*mm, f"No. {dados.get('numero_nfe', '000000000')}")
        c.drawString(x + 45*mm, y - 13*mm, f"Serie: {dados.get('serie', '1')}")

        # Chave de acesso
        chave = dados.get('chave_acesso', '0' * 44)
        c.setFont("Helvetica", 7)
        c.drawString(x + 90*mm, y - 8*mm, "CHAVE DE ACESSO")
        c.setFont("Helvetica-Bold", 8)
        # Formata chave em grupos de 4
        chave_fmt = ' '.join([chave[i:i+4] for i in range(0, 44, 4)])
        c.drawString(x + 90*mm, y - 13*mm, chave_fmt)

        # Protocolo
        c.setFont("Helvetica", 7)
        c.drawString(x + 90*mm, y - 20*mm, "PROTOCOLO DE AUTORIZACAO")
        c.setFont("Helvetica-Bold", 8)
        protocolo = dados.get('protocolo', '')
        data_aut = dados.get('data_autorizacao', '')
        c.drawString(x + 90*mm, y - 25*mm, f"{protocolo} - {data_aut}")

        y -= 35*mm

        # === EMITENTE ===
        c.rect(x, y - 25*mm, width - 2*margin, 25*mm)
        c.setFont("Helvetica", 7)
        c.drawString(x + 2*mm, y - 4*mm, "EMITENTE")
        c.setFont("Helvetica-Bold", 9)
        c.drawString(x + 2*mm, y - 10*mm, dados.get('emit_nome', '')[:60])
        c.setFont("Helvetica", 8)
        c.drawString(x + 2*mm, y - 15*mm, f"CNPJ: {dados.get('emit_cnpj', '')}")
        c.drawString(x + 60*mm, y - 15*mm, f"IE: {dados.get('emit_ie', '')}")
        c.drawString(x + 2*mm, y - 20*mm, dados.get('emit_endereco', '')[:80])

        y -= 30*mm

        # === DESTINATARIO ===
        c.rect(x, y - 20*mm, width - 2*margin, 20*mm)
        c.setFont("Helvetica", 7)
        c.drawString(x + 2*mm, y - 4*mm, "DESTINATARIO/REMETENTE")
        c.setFont("Helvetica-Bold", 9)
        c.drawString(x + 2*mm, y - 10*mm, dados.get('dest_nome', '')[:60])
        c.setFont("Helvetica", 8)
        cpf_cnpj = dados.get('dest_cpf') or dados.get('dest_cnpj', '')
        c.drawString(x + 2*mm, y - 15*mm, f"CPF/CNPJ: {cpf_cnpj}")
        c.drawString(x + 2*mm, y - 20*mm, dados.get('dest_endereco', '')[:80])

        y -= 25*mm

        # === PRODUTOS ===
        c.rect(x, y - 80*mm, width - 2*margin, 80*mm)
        c.setFont("Helvetica-Bold", 8)
        c.drawString(x + 2*mm, y - 5*mm, "DADOS DOS PRODUTOS/SERVICOS")

        # Cabecalho tabela
        c.setFont("Helvetica-Bold", 6)
        col_y = y - 12*mm
        c.drawString(x + 2*mm, col_y, "CODIGO")
        c.drawString(x + 25*mm, col_y, "DESCRICAO")
        c.drawString(x + 100*mm, col_y, "UN")
        c.drawString(x + 115*mm, col_y, "QTD")
        c.drawString(x + 135*mm, col_y, "VL.UNIT")
        c.drawString(x + 160*mm, col_y, "VL.TOTAL")

        c.line(x, col_y - 2*mm, width - margin, col_y - 2*mm)

        # Itens
        c.setFont("Helvetica", 6)
        item_y = col_y - 6*mm
        itens = dados.get('itens', [])
        for item in itens[:15]:  # Limita 15 itens por pagina
            c.drawString(x + 2*mm, item_y, str(item.get('codigo', ''))[:12])
            c.drawString(x + 25*mm, item_y, str(item.get('descricao', ''))[:40])
            c.drawString(x + 100*mm, item_y, str(item.get('unidade', 'UN')))
            c.drawString(x + 115*mm, item_y, f"{item.get('quantidade', 0):.2f}")
            c.drawString(x + 135*mm, item_y, f"{item.get('valor_unitario', 0):.2f}")
            c.drawString(x + 160*mm, item_y, f"{item.get('valor_total', 0):.2f}")
            item_y -= 4*mm

        y -= 85*mm

        # === TOTAIS ===
        c.rect(x, y - 15*mm, width - 2*margin, 15*mm)
        c.setFont("Helvetica", 7)
        c.drawString(x + 2*mm, y - 5*mm, "VALOR TOTAL DOS PRODUTOS")
        c.drawString(x + 50*mm, y - 5*mm, "VALOR DO FRETE")
        c.drawString(x + 90*mm, y - 5*mm, "VALOR DO DESCONTO")
        c.drawString(x + 140*mm, y - 5*mm, "VALOR TOTAL DA NOTA")

        c.setFont("Helvetica-Bold", 9)
        c.drawString(x + 2*mm, y - 12*mm, f"R$ {dados.get('valor_produtos', 0):.2f}")
        c.drawString(x + 50*mm, y - 12*mm, f"R$ {dados.get('valor_frete', 0):.2f}")
        c.drawString(x + 90*mm, y - 12*mm, f"R$ {dados.get('valor_desconto', 0):.2f}")
        c.drawString(x + 140*mm, y - 12*mm, f"R$ {dados.get('valor_total', 0):.2f}")

        y -= 20*mm

        # === INFORMACOES ADICIONAIS ===
        c.rect(x, y - 30*mm, width - 2*margin, 30*mm)
        c.setFont("Helvetica", 7)
        c.drawString(x + 2*mm, y - 5*mm, "INFORMACOES ADICIONAIS")
        c.setFont("Helvetica", 6)
        info = dados.get('informacoes_adicionais', '')
        # Quebra em linhas
        for i, linha in enumerate(info[:300].split('\n')[:5]):
            c.drawString(x + 2*mm, y - 10*mm - (i * 4*mm), linha[:100])

        # Rodape
        c.setFont("Helvetica", 6)
        c.drawString(x, 10*mm, f"Emitido em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
        c.drawString(width - 80*mm, 10*mm, "DANFE gerado por Sistema Enterprise")

        c.save()
        buffer.seek(0)
        return buffer.read()

    def _gerar_danfe_simples(self, dados: Dict[str, Any]) -> bytes:
        """Gera DANFE simples em texto quando ReportLab nao esta disponivel."""
        texto = f"""
================================================================================
                              DANFE - DOCUMENTO AUXILIAR
                           NOTA FISCAL ELETRONICA - NF-e
================================================================================

NUMERO: {dados.get('numero_nfe', '')}                SERIE: {dados.get('serie', '')}
CHAVE DE ACESSO: {dados.get('chave_acesso', '')}
PROTOCOLO: {dados.get('protocolo', '')}

--------------------------------------------------------------------------------
EMITENTE
--------------------------------------------------------------------------------
{dados.get('emit_nome', '')}
CNPJ: {dados.get('emit_cnpj', '')}        IE: {dados.get('emit_ie', '')}
{dados.get('emit_endereco', '')}

--------------------------------------------------------------------------------
DESTINATARIO
--------------------------------------------------------------------------------
{dados.get('dest_nome', '')}
CPF/CNPJ: {dados.get('dest_cpf', '') or dados.get('dest_cnpj', '')}
{dados.get('dest_endereco', '')}

--------------------------------------------------------------------------------
PRODUTOS
--------------------------------------------------------------------------------
"""
        for item in dados.get('itens', []):
            texto += f"{item.get('codigo', '')[:15]:<15} {item.get('descricao', '')[:40]:<40} "
            texto += f"{item.get('quantidade', 0):>8.2f} x {item.get('valor_unitario', 0):>10.2f} = "
            texto += f"{item.get('valor_total', 0):>12.2f}\n"

        texto += f"""
--------------------------------------------------------------------------------
TOTAIS
--------------------------------------------------------------------------------
VALOR PRODUTOS: R$ {dados.get('valor_produtos', 0):.2f}
VALOR FRETE:    R$ {dados.get('valor_frete', 0):.2f}
VALOR DESCONTO: R$ {dados.get('valor_desconto', 0):.2f}
VALOR TOTAL:    R$ {dados.get('valor_total', 0):.2f}

================================================================================
"""
        return texto.encode('utf-8')


# =====================================================
# FUNCOES DE CANCELAMENTO E CARTA DE CORRECAO
# =====================================================

def gerar_xml_cancelamento(
    chave_acesso: str,
    protocolo_autorizacao: str,
    justificativa: str,
    cnpj_emitente: str,
    ambiente: int = 2
) -> str:
    """
    Gera XML de evento de cancelamento de NF-e.

    Args:
        chave_acesso: Chave de acesso da NF-e
        protocolo_autorizacao: Protocolo de autorizacao original
        justificativa: Motivo do cancelamento (min 15 caracteres)
        cnpj_emitente: CNPJ do emitente
        ambiente: 1=Producao, 2=Homologacao

    Returns:
        XML do evento de cancelamento
    """
    # Valida justificativa
    if len(justificativa) < 15:
        justificativa = justificativa.ljust(15)

    data_evento = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S-03:00')
    seq_evento = '1'
    id_evento = f"ID110111{chave_acesso}{seq_evento.zfill(2)}"
    cOrgao = chave_acesso[:2]  # Codigo UF

    xml = f"""<envEvento xmlns="http://www.portalfiscal.inf.br/nfe" versao="1.00">
    <idLote>{datetime.now().strftime('%Y%m%d%H%M%S')}</idLote>
    <evento xmlns="http://www.portalfiscal.inf.br/nfe" versao="1.00">
        <infEvento Id="{id_evento}">
            <cOrgao>{cOrgao}</cOrgao>
            <tpAmb>{ambiente}</tpAmb>
            <CNPJ>{cnpj_emitente}</CNPJ>
            <chNFe>{chave_acesso}</chNFe>
            <dhEvento>{data_evento}</dhEvento>
            <tpEvento>110111</tpEvento>
            <nSeqEvento>{seq_evento}</nSeqEvento>
            <verEvento>1.00</verEvento>
            <detEvento versao="1.00">
                <descEvento>Cancelamento</descEvento>
                <nProt>{protocolo_autorizacao}</nProt>
                <xJust>{justificativa}</xJust>
            </detEvento>
        </infEvento>
    </evento>
</envEvento>"""

    return xml


def gerar_xml_carta_correcao(
    chave_acesso: str,
    texto_correcao: str,
    cnpj_emitente: str,
    sequencia: int = 1,
    ambiente: int = 2
) -> str:
    """
    Gera XML de Carta de Correcao (CC-e).

    Args:
        chave_acesso: Chave de acesso da NF-e
        texto_correcao: Texto da correcao (min 15, max 1000 caracteres)
        cnpj_emitente: CNPJ do emitente
        sequencia: Numero sequencial do evento (1-20)
        ambiente: 1=Producao, 2=Homologacao

    Returns:
        XML do evento de carta de correcao
    """
    # Valida texto
    if len(texto_correcao) < 15:
        texto_correcao = texto_correcao.ljust(15)
    if len(texto_correcao) > 1000:
        texto_correcao = texto_correcao[:1000]

    data_evento = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S-03:00')
    id_evento = f"ID110110{chave_acesso}{str(sequencia).zfill(2)}"
    cOrgao = chave_acesso[:2]

    condicao_uso = ("A Carta de Correcao e disciplinada pelo paragrafo 1o-A do art. 7o "
                    "do Convenio S/N, de 15 de dezembro de 1970 e pode ser utilizada para "
                    "regularizacao de erro ocorrido na emissao de documento fiscal, desde que "
                    "o erro nao esteja relacionado com: I - as variaveis que determinam o valor "
                    "do imposto tais como: base de calculo, aliquota, diferenca de preco, "
                    "quantidade, valor da operacao ou da prestacao; II - a correcao de dados "
                    "cadastrais que implique mudanca do remetente ou do destinatario; "
                    "III - a data de emissao ou de saida.")

    xml = f"""<envEvento xmlns="http://www.portalfiscal.inf.br/nfe" versao="1.00">
    <idLote>{datetime.now().strftime('%Y%m%d%H%M%S')}</idLote>
    <evento xmlns="http://www.portalfiscal.inf.br/nfe" versao="1.00">
        <infEvento Id="{id_evento}">
            <cOrgao>{cOrgao}</cOrgao>
            <tpAmb>{ambiente}</tpAmb>
            <CNPJ>{cnpj_emitente}</CNPJ>
            <chNFe>{chave_acesso}</chNFe>
            <dhEvento>{data_evento}</dhEvento>
            <tpEvento>110110</tpEvento>
            <nSeqEvento>{sequencia}</nSeqEvento>
            <verEvento>1.00</verEvento>
            <detEvento versao="1.00">
                <descEvento>Carta de Correcao</descEvento>
                <xCorrecao>{texto_correcao}</xCorrecao>
                <xCondUso>{condicao_uso}</xCondUso>
            </detEvento>
        </infEvento>
    </evento>
</envEvento>"""

    return xml


# =====================================================
# FUNCAO PARA PROCESSAR CANCELAMENTO
# =====================================================

async def processar_cancelamento_nfe(
    conn: asyncpg.Connection,
    nfe_id: str,
    justificativa: str,
    service: NFeService
) -> Dict[str, Any]:
    """
    Processa cancelamento de NF-e.

    Args:
        conn: Conexao com banco do tenant
        nfe_id: ID da emissao
        justificativa: Motivo do cancelamento
        service: Instancia do NFeService

    Returns:
        Resultado do cancelamento
    """
    try:
        # Busca dados da NF-e
        nfe = await conn.fetchrow(
            "SELECT * FROM nfe_emissions WHERE id = $1",
            nfe_id
        )

        if not nfe:
            return {'success': False, 'error': 'NF-e nao encontrada'}

        if nfe['status'] != 'AUTHORIZED':
            return {'success': False, 'error': f'NF-e nao pode ser cancelada. Status: {nfe["status"]}'}

        if not nfe['chave_acesso'] or not nfe['protocolo_autorizacao']:
            return {'success': False, 'error': 'NF-e sem chave de acesso ou protocolo'}

        # Verifica prazo (24 horas em producao, sem limite em homologacao)
        if nfe['ambiente'] == 1:  # Producao
            data_autorizacao = nfe['data_autorizacao']
            if data_autorizacao:
                horas = (datetime.now() - data_autorizacao).total_seconds() / 3600
                if horas > 24:
                    return {
                        'success': False,
                        'error': 'Prazo de 24 horas para cancelamento expirado'
                    }

        # Busca configuracoes fiscais
        fiscal = await conn.fetchrow(
            "SELECT * FROM fiscal_settings WHERE is_active = TRUE LIMIT 1"
        )

        if not fiscal:
            return {'success': False, 'error': 'Configuracoes fiscais nao encontradas'}

        # Busca CNPJ da empresa
        company = await conn.fetchrow("SELECT document FROM companies LIMIT 1")
        cnpj = (company['document'] or '').replace('.', '').replace('/', '').replace('-', '')

        # Gera XML de cancelamento
        xml_cancelamento = gerar_xml_cancelamento(
            chave_acesso=nfe['chave_acesso'],
            protocolo_autorizacao=nfe['protocolo_autorizacao'],
            justificativa=justificativa,
            cnpj_emitente=cnpj,
            ambiente=nfe['ambiente']
        )

        # Carrega certificado e assina
        service.load_certificate(
            fiscal['certificate_file'],
            fiscal['certificate_password_encrypted']
        )
        xml_assinado = service.assinar_xml(xml_cancelamento)

        # Em homologacao, simula sucesso
        if nfe['ambiente'] == 2:
            protocolo_cancel = f"CANC{datetime.now().strftime('%Y%m%d%H%M%S')}"

            await conn.execute("""
                UPDATE nfe_emissions SET
                    status = 'CANCELLED',
                    cancelled_at = CURRENT_TIMESTAMP,
                    motivo_cancelamento = $1,
                    protocolo_cancelamento = $2,
                    xml_cancelamento = $3,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = $4
            """, justificativa, protocolo_cancel, xml_assinado, nfe_id)

            return {
                'success': True,
                'protocolo': protocolo_cancel,
                'message': 'NF-e cancelada com sucesso (homologacao)'
            }

        # Em producao, envia para SEFAZ
        url = service.get_sefaz_url(fiscal['uf'], 'RecepcaoEvento', nfe['ambiente'])
        if not url:
            return {'success': False, 'error': 'URL do servico nao encontrada'}

        # Cria cliente SEFAZ
        client = SefazClient(
            fiscal['certificate_file'],
            service._decrypt_password(fiscal['certificate_password_encrypted'])
        )

        result = client.enviar_evento(xml_assinado, url)

        if result.get('success'):
            await conn.execute("""
                UPDATE nfe_emissions SET
                    status = 'CANCELLED',
                    cancelled_at = CURRENT_TIMESTAMP,
                    motivo_cancelamento = $1,
                    protocolo_cancelamento = $2,
                    xml_cancelamento = $3,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = $4
            """, justificativa, result.get('protocolo'), xml_assinado, nfe_id)

        return result

    except Exception as e:
        logger.error(f"Erro ao cancelar NF-e: {e}")
        return {'success': False, 'error': str(e)}
