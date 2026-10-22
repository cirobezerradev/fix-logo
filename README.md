# � FixLogo

Aplicação web que **fixa automaticamente** a logomarca do petshop no **canto inferior
esquerdo** das fotos dos pets, pronta para publicação no Instagram.

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

Cobrem upload JPG/PNG, posição da logo, dimensões de saída, pré-visualização,
download, validação de formato/tamanho, exclusão, limpeza por TTL e ausência da logo.

---

## 🔌 API

| Método | Rota | Descrição |
| :--- | :--- | :--- |
| `GET` | `/api/health` | Status do servidor e disponibilidade da logo |
| `GET` | `/api/config` | Limites de upload e regras de sobreposição |
| `POST` | `/api/process` | Recebe `multipart/form-data` no campo `file` (JPG/PNG) |
| `GET` | `/api/images/{id}/preview` | Pré-visualização leve (JPEG ≤ 1400 px) |
| `GET` | `/api/images/{id}/download` | Imagem final com `Content-Disposition: attachment` |
| `DELETE` | `/api/images/{id}` | Remove a imagem do storage imediatamente |
| `GET` | `/docs` | Documentação interativa (Swagger UI) |

Exemplo com `curl`:

```bash
curl -F "file=@foto-do-pet.jpg" http://127.0.0.1:8000/api/process
```

Resposta:

```json
{
  "id": "54158067df1c46338ba6b1e9fc6b7045",
  "download_name": "foto-do-pet-logo.jpg",
  "width": 1800,
  "height": 1350,
  "logo_width": 324,
  "preview_url": "/api/images/54158067df1c46338ba6b1e9fc6b7045/preview",
  "download_url": "/api/images/54158067df1c46338ba6b1e9fc6b7045/download",
  "expires_in_minutes": 60,
  "processing_ms": 226
}
```

---

## ⚙️ Configuração (variáveis de ambiente)

| Variável | Padrão | Descrição |
| :--- | :--- | :--- |
| `LOGO_PATH` | `backend/logo/logo_petshop.png` | Caminho da logomarca |
| `STORAGE_DIR` | `backend/storage` | Pasta das imagens temporárias |
| `MAX_UPLOAD_BYTES` | `26214400` (25 MB) | Limite de upload |
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

## ✅ Cobertura dos requisitos

| ID | Requisito | Onde |
| :--- | :--- | :--- |
| RF01 | Upload JPG/JPEG/PNG | `frontend/index.html`, `backend/app.py` |
| RF02 | Aplicação da logo fixa com transparência e escala | `backend/image_processing.py` |
| RF03 | Visualização prévia com comparador antes/depois | `frontend/index.html`, `frontend/app.js` |
| RF04 | Download em alta qualidade | `/api/images/{id}/download` |
| RF05 | Limpeza automática de arquivos temporários | `backend/storage.py`, lifespan em `app.py` |
| RNF | Processamento < 2 s | ~200–300 ms para fotos de 1800×1350 |
