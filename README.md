# 📌 FixLogo

Aplicação web que **fixa automaticamente** a logomarca do petshop no **canto inferior
esquerdo** das fotos dos pets, pronta para publicação no Instagram.

- **Envio em lote:** o usuário envia quantas fotos quiser, de uma vez ou em envios
  sucessivos, sem limite de quantidade na interface.
- **Download individual:** cada foto processada recebe o seu próprio link de download.
- **Compartilhar no Instagram (mobile):** botão que abre o menu nativo do sistema
  (Web Share API) para publicar direto no app, escrevendo a legenda lá dentro.
- **Sem pré-visualização:** a tela mostra apenas nome, status e link de cada foto.
- **Frontend:** HTML5 + Tailwind CSS + JavaScript (Fetch API), responsivo.
- **Backend:** Python + FastAPI + Pillow.
- **Sem login**, sem banco de dados: as fotos processadas ficam em disco apenas por
  tempo limitado e são removidas automaticamente.

---

## 📁 Estrutura do projeto

```text
logo-photo-pet/
├── backend/
│   ├── logo/
│   │   └── logo_petshop.png     # logomarca fixa (substitua pela arte oficial)
│   ├── storage/                 # gerado em runtime (imagens temporárias)
│   ├── app.py                   # API FastAPI + servidor do frontend
│   ├── config.py                # configurações via variáveis de ambiente
│   ├── image_processing.py      # regra de sobreposição da logo (Pillow)
│   ├── storage.py               # armazenamento temporário + limpeza
│   ├── requirements.txt
│   └── requirements-dev.txt
├── frontend/
│   ├── index.html
│   ├── styles.css
│   ├── app.js
│   └── favicon.svg
├── scripts/
│   └── generate_logo.py         # gera uma logo provisória com transparência
├── tests/
│   └── test_api.py
└── README.md
```

---

## 🚀 Como executar

```bash
# 1. Ambiente virtual (a pasta .venv já existe neste projeto)
python3 -m venv .venv
source .venv/bin/activate

# 2. Dependências
pip install -r backend/requirements.txt

# 3. Servidor (a partir da raiz do projeto)
uvicorn backend.app:app --reload --port 8000
```

Abra **http://127.0.0.1:8000** — o FastAPI já serve o frontend na raiz.

> A logomarca provisória já foi gerada em `backend/logo/logo_petshop.png`.
> Para usar a logo real, basta substituir esse arquivo por um PNG com transparência
> (a troca é detectada automaticamente, sem reiniciar o servidor).

Para regenerar a logo provisória:

```bash
python scripts/generate_logo.py
```

---

## 🧪 Testes

```bash
pip install -r backend/requirements-dev.txt
pytest tests -q
```

Cobrem upload individual e em lote, links de download por foto, posição da logo,
dimensões de saída, validação de formato/tamanho/megapixels, erros individualizados
no lote, exclusão, limpeza por TTL e ausência da logo.

---

## ☁️ Deploy no Render

O projeto já inclui o `requirements.txt` na raiz (que aponta para as dependências do
backend) e o blueprint `render.yaml`.

### Opção 1 — Blueprint (recomendada)

1. Suba o código para um repositório no GitHub/GitLab.
2. No [Render Dashboard](https://dashboard.render.com), clique em **New +** → **Blueprint**.
3. Selecione o repositório. O Render lê o `render.yaml` e cria o serviço web.
4. Aguarde o build; a aplicação fica em `https://<nome-do-servico>.onrender.com`.

### Opção 2 — Configuração manual

Crie um **Web Service** com runtime **Python** e preencha:

| Campo | Valor |
| :--- | :--- |
| Build Command | `pip install --upgrade pip && pip install -r requirements.txt` |
| Start Command | `uvicorn backend.app:app --host 0.0.0.0 --port $PORT` |
| Health Check Path | `/api/health` |
| Variável de ambiente | `PYTHON_VERSION=3.13.7` (ajuste para uma versão disponível) |

### Pontos de atenção

- **Disco efêmero:** as fotos processadas ficam no disco do container e são perdidas a
  cada deploy/restart. A limpeza por TTL continua funcionando. Para persistência,
  adicione um **Render Disk** e aponte `STORAGE_DIR` para o ponto de montagem.
- **Logo:** `backend/logo/logo_petshop.png` está versionado no repositório — para trocar,
  faça commit da nova imagem. A pasta `backend/storage/` está no `.gitignore`.
- **Plano Free:** o serviço hiberna após inatividade; a primeira requisição pode demorar
  alguns segundos.
- **Memória:** o plano Free tem 512 MB de RAM. Por isso o `render.yaml` define
  `MAX_IMAGE_PIXELS=32000000` (32 MP) — fotos maiores são recusadas com mensagem clara,
  em vez de derrubar o processo. Em planos maiores, aumente o valor (pico medido:
  ~270 MB para uma foto de 24 MP).
- **Lote no Render:** o `render.yaml` define `MAX_BATCH_BYTES=94371840` (90 MB) para ficar
  abaixo do limite de payload do proxy. O frontend envia em blocos de até 10 fotos **e**
  respeita esse limite de bytes, consultando `max_batch_mb` em `/api/config`.
- **Frontend:** é servido pelo próprio FastAPI na rota `/`, sem build separado.

---

## 🔌 API

| Método | Rota | Descrição |
| :--- | :--- | :--- |
| `GET` | `/api/health` | Status do servidor e disponibilidade da logo |
| `GET` | `/api/config` | Limites de upload/lote e regras de sobreposição |
| `POST` | `/api/process` | Recebe `multipart/form-data` com o campo repetido `files` (1..N JPG/PNG) |
| `GET` | `/api/images/{id}/download` | Imagem final com `Content-Disposition: attachment` |
| `DELETE` | `/api/images/{id}` | Remove a imagem do storage imediatamente |
| `GET` | `/docs` | Documentação interativa (Swagger UI) |

Não existe rota de pré-visualização: o resultado é entregue apenas pelos links
individuais de download.

Exemplo com `curl` (três fotos em um único lote):

```bash
curl -F "files=@foto-1.jpg" \
     -F "files=@foto-2.png" \
     -F "files=@foto-3.jpg" \
     http://127.0.0.1:8000/api/process
```

Resposta (resumo):

```json
{
  "total": 3,
  "succeeded": 2,
  "failed": 1,
  "expires_in_minutes": 60,
  "processing_ms": 812,
  "items": [
    {
      "ok": true,
      "id": "54158067df1c46338ba6b1e9fc6b7045",
      "original_name": "foto-1.jpg",
      "download_name": "foto-1-logo.jpg",
      "media_type": "image/jpeg",
      "width": 1800,
      "height": 1350,
      "logo_width": 405,
      "logo_height": 366,
      "download_url": "/api/images/54158067df1c46338ba6b1e9fc6b7045/download",
      "processing_ms": 226
    },
    {
      "ok": false,
      "original_name": "arquivo-invalido.txt",
      "error": "Formato não suportado. Envie imagens JPG, JPEG ou PNG."
    }
  ]
}
```

Cada item traz o seu próprio `download_url`. Um arquivo inválido não interrompe o
processamento dos demais.

---

## ⚙️ Configuração (variáveis de ambiente)

| Variável | Padrão | Descrição |
| :--- | :--- | :--- |
| `LOGO_PATH` | `backend/logo/logo_petshop.png` | Caminho da logomarca |
| `STORAGE_DIR` | `backend/storage` | Pasta das imagens temporárias |
| `MAX_UPLOAD_BYTES` | `26214400` (25 MB) | Limite por foto |
| `MAX_BATCH_FILES` | `20` | Fotos por requisição (a interface envia em blocos de 10) |
| `MAX_BATCH_BYTES` | `125829120` (120 MB) | Tamanho total de um lote (90 MB no `render.yaml`) |
| `MAX_IMAGE_PIXELS` | `60000000` | Proteção contra imagens gigantes |
| `LOGO_WIDTH_RATIO` | `0.225` | Largura da logo (22,5% da largura da foto) |
| `LOGO_MIN_WIDTH_RATIO` / `LOGO_MAX_WIDTH_RATIO` | `0.10` / `0.40` | Limites de escala |
| `LOGO_PADDING_RATIO` | `0.025` | Margem em relação ao menor lado |
| `LOGO_PADDING_MIN_PX` | `12` | Margem mínima em pixels |
| `LOGO_OPACITY` | `1.0` | Opacidade da logo (0–1) |
| `JPEG_QUALITY` | `92` | Qualidade de saída JPG |
| `FILE_TTL_SECONDS` | `3600` | Tempo de vida das imagens no servidor |
| `CLEANUP_INTERVAL_SECONDS` | `900` | Intervalo da limpeza automática |
| `ALLOWED_ORIGINS` | `*` | Origens permitidas no CORS |

Exemplo:

```bash
LOGO_WIDTH_RATIO=0.22 FILE_TTL_SECONDS=1800 uvicorn backend.app:app --port 8000
```

---

## 🖼️ Regra de sobreposição

1. A foto é aberta com Pillow e a orientação EXIF é corrigida automaticamente.
2. A logo é redimensionada proporcionalmente para **22,5% da largura da foto**
   (entre 10% e 40%, com largura mínima de 48 px).
3. A margem é **2,5% do menor lado da imagem** (mínimo de 12 px).
4. A composição usa o canal alpha do PNG, no canto **inferior esquerdo**.
5. A saída mantém o formato de origem: **JPEG** (qualidade 92, progressivo) ou
   **PNG** (se a origem for PNG). Metadados/EXIF não são repassados.

---

## 📲 Compartilhar no Instagram

Em cada foto processada, dispositivos compatíveis exibem o botão **Compartilhar**. Ele usa a
Web Share API (`navigator.share` com arquivo) para abrir o menu nativo do sistema:

1. Toque em **Compartilhar** na foto desejada.
2. Escolha o **Instagram** no menu do sistema.
3. O Instagram abre o fluxo de publicação com a imagem — escreva a legenda e confirme.

Limitações (definidas pelo Instagram e pelo sistema operacional, não pelo site):

- O site **não** consegue pré-preencher a legenda nem forçar a escolha feed/story.
- Em alguns aparelhos o Instagram abre direto em *Stories*; nesse caso, alterne para *Feed*
  dentro do app.
- Requer **HTTPS** (o Render já fornece) e navegador com suporte a compartilhamento de
  arquivos (Chrome no Android, Safari no iOS, entre outros).
- Sem suporte, o botão **Baixar** permanece disponível e o compartilhamento é ocultado.

---

## ✅ Cobertura dos requisitos

| ID | Requisito | Onde |
| :--- | :--- | :--- |
| RF01 | Upload de uma ou várias imagens JPG/JPEG/PNG | `frontend/index.html`, `backend/app.py` |
| RF02 | Aplicação da logo fixa com transparência e escala | `backend/image_processing.py` |
| RF03 | Resultado sem prévia (nome, status e link) | `frontend/app.js` |
| RF04 | Download em alta qualidade | `/api/images/{id}/download` |
| RF05 | Limpeza automática de arquivos temporários | `backend/storage.py`, lifespan em `app.py` |
| RF06 | Envio em lote (quantas fotos quiser) | campo repetido `files`, `frontend/app.js` |
| RF07 | Link de download individual por foto | `items[].download_url` na resposta de `/api/process` |
| RF08 | Compartilhar no Instagram (mobile) | `navigator.share` com arquivo em `frontend/app.js` |
| RNF | Processamento < 2 s por foto | ~200–300 ms para fotos de 1800×1350 |
