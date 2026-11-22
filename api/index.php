<?php
header('Content-Type: application/json; charset=utf-8');
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: GET, POST, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type');

if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') {
    http_response_code(204);
    exit;
}

$baseDir = dirname(__DIR__);
$dataFile = $baseDir . DIRECTORY_SEPARATOR . 'data' . DIRECTORY_SEPARATOR . 'ocorrencias.json';
$douDir = $baseDir . DIRECTORY_SEPARATOR . 'dou-sj';
$analyzerScript = $baseDir . DIRECTORY_SEPARATOR . 'analyzer' . DIRECTORY_SEPARATOR . 'analisar_dou.py';

$action = $_GET['action'] ?? 'list';

if ($action === 'list') {
    if (!file_exists($dataFile)) {
        echo json_encode(['gerado_em' => null, 'total' => 0, 'arquivos_analisados' => [], 'ocorrencias' => []], JSON_UNESCAPED_UNICODE);
        exit;
    }
    echo file_get_contents($dataFile);
    exit;
}

if ($action === 'analyze') {
    $enrich = isset($_GET['enrich']) && $_GET['enrich'] === '1' ? ' --enrich' : '';
    $cmd = 'python ' . escapeshellarg($analyzerScript) . $enrich . ' 2>&1';
    $output = shell_exec($cmd);
    if (!file_exists($dataFile)) {
        http_response_code(500);
        echo json_encode(['error' => 'Falha ao executar analisador.', 'log' => $output], JSON_UNESCAPED_UNICODE);
        exit;
    }
    $data = json_decode(file_get_contents($dataFile), true);
    $data['analyzer_log'] = $output;
    echo json_encode($data, JSON_UNESCAPED_UNICODE);
    exit;
}

if ($action === 'upload' && $_SERVER['REQUEST_METHOD'] === 'POST') {
    if (!isset($_FILES['pdf']) || $_FILES['pdf']['error'] !== UPLOAD_ERR_OK) {
        http_response_code(400);
        echo json_encode(['error' => 'Arquivo PDF inválido ou ausente.'], JSON_UNESCAPED_UNICODE);
        exit;
    }
    $name = basename($_FILES['pdf']['name']);
    if (!preg_match('/\.pdf$/i', $name)) {
        http_response_code(400);
        echo json_encode(['error' => 'Apenas arquivos .pdf são permitidos.'], JSON_UNESCAPED_UNICODE);
        exit;
    }
    $safeName = preg_replace('/[^a-zA-Z0-9_\-\.]/', '_', $name);
    $dest = $douDir . DIRECTORY_SEPARATOR . $safeName;
    if (!move_uploaded_file($_FILES['pdf']['tmp_name'], $dest)) {
        http_response_code(500);
        echo json_encode(['error' => 'Não foi possível salvar o arquivo em dou-sj/.'], JSON_UNESCAPED_UNICODE);
        exit;
    }
    $cmd = 'python ' . escapeshellarg($analyzerScript) . ' --enrich 2>&1';
    $output = shell_exec($cmd);
    $data = file_exists($dataFile) ? json_decode(file_get_contents($dataFile), true) : ['ocorrencias' => []];
    $data['uploaded'] = $safeName;
    $data['analyzer_log'] = $output;
    echo json_encode($data, JSON_UNESCAPED_UNICODE);
    exit;
}

if ($action === 'save' && $_SERVER['REQUEST_METHOD'] === 'POST') {
    $raw = file_get_contents('php://input');
    $body = json_decode($raw, true);
    if (!$body || !isset($body['ocorrencias']) || !is_array($body['ocorrencias'])) {
        http_response_code(400);
        echo json_encode(['error' => 'Payload inválido.'], JSON_UNESCAPED_UNICODE);
        exit;
    }
    $body['atualizado_em'] = date('c');
    file_put_contents($dataFile, json_encode($body, JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT));
    echo json_encode(['ok' => true, 'total' => count($body['ocorrencias'])], JSON_UNESCAPED_UNICODE);
    exit;
}

if ($action === 'lookup_cnpj') {
    $cnpj = preg_replace('/\D/', '', $_GET['cnpj'] ?? '');
    if (strlen($cnpj) !== 14) {
        http_response_code(400);
        echo json_encode(['error' => 'CNPJ deve ter 14 dígitos.'], JSON_UNESCAPED_UNICODE);
        exit;
    }
    $ctx = stream_context_create([
        'http' => [
            'timeout' => 10,
            'header' => "User-Agent: SentinelaDiario/1.0\r\n"
        ]
    ]);
    $res = @file_get_contents("https://brasilapi.com.br/api/cnpj/v1/{$cnpj}", false, $ctx);
    if ($res === false) {
        http_response_code(502);
        echo json_encode(['error' => 'Não foi possível consultar o CNPJ na BrasilAPI.'], JSON_UNESCAPED_UNICODE);
        exit;
    }
    echo $res;
    exit;
}

if ($action === 'get_settings') {
    $settingsFile = $baseDir . DIRECTORY_SEPARATOR . 'data' . DIRECTORY_SEPARATOR . 'settings.json';
    $settings = file_exists($settingsFile) ? json_decode(file_get_contents($settingsFile), true) : [];
    if (!is_array($settings)) {
        $settings = [];
    }
    $settings = array_merge(['email_auto_enabled' => false], $settings);
    echo json_encode($settings, JSON_UNESCAPED_UNICODE);
    exit;
}

if ($action === 'set_settings' && $_SERVER['REQUEST_METHOD'] === 'POST') {
    $raw = file_get_contents('php://input');
    $body = json_decode($raw, true);
    if (!is_array($body) || !array_key_exists('email_auto_enabled', $body)) {
        http_response_code(400);
        echo json_encode(['error' => 'Payload inválido.'], JSON_UNESCAPED_UNICODE);
        exit;
    }
    $settingsFile = $baseDir . DIRECTORY_SEPARATOR . 'data' . DIRECTORY_SEPARATOR . 'settings.json';
    $settings = file_exists($settingsFile) ? json_decode(file_get_contents($settingsFile), true) : [];
    if (!is_array($settings)) {
        $settings = [];
    }
    $settings['email_auto_enabled'] = (bool)$body['email_auto_enabled'];
    $settings['atualizado_em'] = date('c');
    file_put_contents($settingsFile, json_encode($settings, JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT));
    echo json_encode($settings, JSON_UNESCAPED_UNICODE);
    exit;
}

if ($action === 'send_email' && $_SERVER['REQUEST_METHOD'] === 'POST') {
    $raw = file_get_contents('php://input');
    $body = json_decode($raw, true);
    if (!$body || empty($body['to']) || empty($body['subject']) || (empty($body['html']) && empty($body['text']))) {
        http_response_code(400);
        echo json_encode(['error' => 'Campos obrigatórios: to, subject e (html ou text).'], JSON_UNESCAPED_UNICODE);
        exit;
    }

    $configFile = $baseDir . DIRECTORY_SEPARATOR . 'data' . DIRECTORY_SEPARATOR . 'resend_config.json';
    $config = file_exists($configFile) ? json_decode(file_get_contents($configFile), true) : [];
    $apiKey = getenv('RESEND_API_KEY') ?: ($config['api_key'] ?? '');
    $defaultFrom = $config['from'] ?? 'Sentinela Diário <contato@sentineladiario.com>';

    $signatureHtml = <<<'HTML'
<br><br>
<table cellpadding="0" cellspacing="0" border="0" style="font-family: Arial, Helvetica, sans-serif; font-size: 13px; line-height: 1.4; color: #333333; max-width: 480px;">
  <tr>
    <td style="padding-right: 14px; border-right: 3px solid #0F172A; vertical-align: middle;">
      <div style="width: 44px; height: 44px; background-color: #0F172A; border-radius: 8px; text-align: center; line-height: 44px; color: #38BDF8; font-weight: bold; font-size: 18px;">
        SD
      </div>
    </td>
    <td style="padding-left: 14px; vertical-align: middle;">
      <div style="font-size: 15px; font-weight: bold; color: #0F172A;">
        Renato
      </div>
      <div style="font-size: 12px; color: #475569; margin-bottom: 6px;">
        Monitoramento Inteligente de CNPJ &amp; Diários Oficiais
      </div>
      <div style="font-size: 12px; color: #0F172A;">
        <a href="https://wa.me/5512991530244" target="_blank" rel="noopener noreferrer" style="color: #059669; text-decoration: none; font-weight: bold;">
          WhatsApp: (12) 99153-0244
        </a>
        <span style="color: #CBD5E1; margin: 0 6px;">|</span>
        <a href="https://sentineladiario.com/" target="_blank" rel="noopener noreferrer" style="color: #2563EB; text-decoration: none;">
          sentineladiario.com
        </a>
      </div>
    </td>
  </tr>
</table>
HTML;

    $signatureText = "\n\n--\nRenato\nMonitoramento Inteligente de CNPJ & Diários Oficiais\nWhatsApp: (12) 99153-0244 | https://sentineladiario.com/";

    $payload = [
        'from' => !empty($body['from']) ? $body['from'] : $defaultFrom,
        'to' => is_array($body['to']) ? $body['to'] : [$body['to']],
        'subject' => $body['subject'],
    ];
    if (!empty($body['html'])) {
        $payload['html'] = $body['html'] . $signatureHtml;
    }
    if (!empty($body['text'])) {
        $payload['text'] = $body['text'] . $signatureText;
    }

    if (!empty($body['dry_run'])) {
        echo json_encode(['ok' => true, 'dry_run' => true, 'payload' => $payload], JSON_UNESCAPED_UNICODE);
        exit;
    }

    if (empty($apiKey) || str_contains($apiKey, 'COLOQUE_SUA_API_KEY')) {
        http_response_code(500);
        echo json_encode(['error' => 'RESEND_API_KEY não configurada em data/resend_config.json ou variável de ambiente.'], JSON_UNESCAPED_UNICODE);
        exit;
    }

    $ch = curl_init('https://api.resend.com/emails');
    curl_setopt_array($ch, [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_POST => true,
        CURLOPT_TIMEOUT => 15,
        CURLOPT_HTTPHEADER => [
            'Authorization: Bearer ' . $apiKey,
            'Content-Type: application/json',
        ],
        CURLOPT_POSTFIELDS => json_encode($payload, JSON_UNESCAPED_UNICODE),
    ]);
    $response = curl_exec($ch);
    $httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    $curlErr = curl_error($ch);
    curl_close($ch);

    if ($response === false) {
        http_response_code(502);
        echo json_encode(['error' => 'Falha na conexão com Resend.', 'detail' => $curlErr], JSON_UNESCAPED_UNICODE);
        exit;
    }

    http_response_code($httpCode ?: 200);
    echo $response;
    exit;
}

http_response_code(404);
echo json_encode(['error' => 'Ação desconhecida.'], JSON_UNESCAPED_UNICODE);
