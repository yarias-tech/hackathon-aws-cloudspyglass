export type Language = 'en' | 'es' | 'pt';

export interface Translations {
  // NavHeader
  nav_diagram: string;
  nav_settings: string;

  // ScanControls
  scan_button: string;
  scan_scanning: string;
  scan_stop: string;
  scan_elapsed: string;

  // SettingsPage
  settings_title: string;
  settings_credential_status: string;
  settings_loading_status: string;
  settings_connected: string;
  settings_disconnected: string;
  settings_expired: string;
  settings_account_id: string;
  settings_source: string;
  settings_source_ui: string;
  settings_source_boto3: string;
  settings_expiry: string;
  settings_no_expiration: string;
  settings_disconnect: string;
  settings_disconnecting: string;
  settings_credentials: string;
  settings_access_key_id: string;
  settings_secret_access_key: string;
  settings_session_token: string;
  settings_session_token_optional: string;
  settings_default_region: string;
  settings_submit: string;
  settings_submitting: string;
  settings_auto_refresh: string;
  settings_auto_refresh_interval: string;
  settings_regions: string;
  settings_select_regions: string;

  // About section
  about_title: string;
  about_description: string;
  about_authors: string;
  about_source_code: string;
  about_built_with: string;

  // Auto-refresh options
  auto_refresh_manual: string;
  auto_refresh_1m: string;
  auto_refresh_5m: string;
  auto_refresh_15m: string;
  auto_refresh_30m: string;
  auto_refresh_60m: string;

  // Language selector
  language_label: string;
}

const en: Translations = {
  nav_diagram: 'Diagram',
  nav_settings: 'Settings',

  scan_button: 'Scan',
  scan_scanning: 'Scanning…',
  scan_stop: 'Stop',
  scan_elapsed: 'Elapsed',

  settings_title: 'Settings',
  settings_credential_status: 'Credential Status',
  settings_loading_status: 'Loading status…',
  settings_connected: 'Connected',
  settings_disconnected: 'Disconnected',
  settings_expired: 'Expired',
  settings_account_id: 'Account ID',
  settings_source: 'Source',
  settings_source_ui: 'UI-provided',
  settings_source_boto3: 'boto3 chain',
  settings_expiry: 'Expiry',
  settings_no_expiration: 'No expiration',
  settings_disconnect: 'Disconnect',
  settings_disconnecting: 'Disconnecting…',
  settings_credentials: 'AWS Credentials',
  settings_access_key_id: 'Access Key ID',
  settings_secret_access_key: 'Secret Access Key',
  settings_session_token: 'Session Token',
  settings_session_token_optional: '(optional)',
  settings_default_region: 'Default Region',
  settings_submit: 'Connect',
  settings_submitting: 'Connecting…',
  settings_auto_refresh: 'Auto-Refresh',
  settings_auto_refresh_interval: 'Refresh Interval',
  settings_regions: 'Regions',
  settings_select_regions: 'Select regions to scan',

  about_title: 'About CloudSpyglass',
  about_description: 'Your entire AWS infrastructure, visualized in one click. Scans 30+ resource types across all regions, detects network/IAM/event/data relationships automatically, and renders a live interactive diagram. No agents, no complex setup — just connect and scan.',
  about_authors: 'Authors',
  about_source_code: 'Source Code',
  about_built_with: 'Built with React, FastAPI, and boto3. Deployed on AWS ECS Fargate.',

  auto_refresh_manual: 'Manual',
  auto_refresh_1m: '1 minute',
  auto_refresh_5m: '5 minutes',
  auto_refresh_15m: '15 minutes',
  auto_refresh_30m: '30 minutes',
  auto_refresh_60m: '60 minutes',

  language_label: 'Language',
};

const es: Translations = {
  nav_diagram: 'Diagrama',
  nav_settings: 'Configuración',

  scan_button: 'Escanear',
  scan_scanning: 'Escaneando…',
  scan_stop: 'Detener',
  scan_elapsed: 'Transcurrido',

  settings_title: 'Configuración',
  settings_credential_status: 'Estado de Credenciales',
  settings_loading_status: 'Cargando estado…',
  settings_connected: 'Conectado',
  settings_disconnected: 'Desconectado',
  settings_expired: 'Expirado',
  settings_account_id: 'ID de Cuenta',
  settings_source: 'Origen',
  settings_source_ui: 'Proporcionado por UI',
  settings_source_boto3: 'Cadena boto3',
  settings_expiry: 'Expiración',
  settings_no_expiration: 'Sin expiración',
  settings_disconnect: 'Desconectar',
  settings_disconnecting: 'Desconectando…',
  settings_credentials: 'Credenciales AWS',
  settings_access_key_id: 'Access Key ID',
  settings_secret_access_key: 'Secret Access Key',
  settings_session_token: 'Session Token',
  settings_session_token_optional: '(opcional)',
  settings_default_region: 'Región por Defecto',
  settings_submit: 'Conectar',
  settings_submitting: 'Conectando…',
  settings_auto_refresh: 'Auto-Refresh',
  settings_auto_refresh_interval: 'Intervalo de Actualización',
  settings_regions: 'Regiones',
  settings_select_regions: 'Seleccionar regiones a escanear',

  about_title: 'Acerca de CloudSpyglass',
  about_description: 'Toda tu infraestructura AWS, visualizada en un click. Escanea más de 30 tipos de recursos en todas las regiones, detecta relaciones de red/IAM/eventos/datos automáticamente, y genera un diagrama interactivo en vivo. Sin agentes, sin configuración compleja — solo conecta y escanea.',
  about_authors: 'Autores',
  about_source_code: 'Código Fuente',
  about_built_with: 'Construido con React, FastAPI y boto3. Desplegado en AWS ECS Fargate.',

  auto_refresh_manual: 'Manual',
  auto_refresh_1m: '1 minuto',
  auto_refresh_5m: '5 minutos',
  auto_refresh_15m: '15 minutos',
  auto_refresh_30m: '30 minutos',
  auto_refresh_60m: '60 minutos',

  language_label: 'Idioma',
};

const pt: Translations = {
  nav_diagram: 'Diagrama',
  nav_settings: 'Configurações',

  scan_button: 'Escanear',
  scan_scanning: 'Escaneando…',
  scan_stop: 'Parar',
  scan_elapsed: 'Decorrido',

  settings_title: 'Configurações',
  settings_credential_status: 'Status das Credenciais',
  settings_loading_status: 'Carregando status…',
  settings_connected: 'Conectado',
  settings_disconnected: 'Desconectado',
  settings_expired: 'Expirado',
  settings_account_id: 'ID da Conta',
  settings_source: 'Origem',
  settings_source_ui: 'Fornecido pela UI',
  settings_source_boto3: 'Cadeia boto3',
  settings_expiry: 'Expiração',
  settings_no_expiration: 'Sem expiração',
  settings_disconnect: 'Desconectar',
  settings_disconnecting: 'Desconectando…',
  settings_credentials: 'Credenciais AWS',
  settings_access_key_id: 'Access Key ID',
  settings_secret_access_key: 'Secret Access Key',
  settings_session_token: 'Session Token',
  settings_session_token_optional: '(opcional)',
  settings_default_region: 'Região Padrão',
  settings_submit: 'Conectar',
  settings_submitting: 'Conectando…',
  settings_auto_refresh: 'Auto-Refresh',
  settings_auto_refresh_interval: 'Intervalo de Atualização',
  settings_regions: 'Regiões',
  settings_select_regions: 'Selecionar regiões para escanear',

  about_title: 'Sobre o CloudSpyglass',
  about_description: 'Toda a sua infraestrutura AWS, visualizada em um clique. Escaneia mais de 30 tipos de recursos em todas as regiões, detecta relacionamentos de rede/IAM/eventos/dados automaticamente, e gera um diagrama interativo ao vivo. Sem agentes, sem configuração complexa — apenas conecte e escaneie.',
  about_authors: 'Autores',
  about_source_code: 'Código Fonte',
  about_built_with: 'Construído com React, FastAPI e boto3. Implantado no AWS ECS Fargate.',

  auto_refresh_manual: 'Manual',
  auto_refresh_1m: '1 minuto',
  auto_refresh_5m: '5 minutos',
  auto_refresh_15m: '15 minutos',
  auto_refresh_30m: '30 minutos',
  auto_refresh_60m: '60 minutos',

  language_label: 'Idioma',
};

export const translations: Record<Language, Translations> = { en, es, pt };
