# Documento de Requisitos do Produto (PRD)

## 1. Visão Geral do Produto

* **Nome do Projeto:** PetShop Watermark Automator
* **Objetivo:** Automatizar a aplicação da logomarca do petshop no canto inferior esquerdo das fotos dos animais de estimação, eliminando o processo manual de edição para publicação no feed do Instagram. A aplicação deve permitir o envio de várias fotos em lote e devolver, para cada foto, um link individual de download.
* **Público-Alvo:** Funcionários e equipe de marketing do petshop.

---

## 2. Escopo do Sistema

### 2.1 O que o sistema FAZ (In-Scope)
* Interface web minimalista e responsiva para upload de imagem pelo usuário.
* Envio de **quantas fotos o usuário quiser**, em lote, em uma mesma operação ou em envios sucessivos, sem limite de quantidade imposto pela interface.
* Envio da foto original para o backend em Python.
* Processamento da imagem no backend inserindo a logo fixa (armazenada localmente na pasta `logo/`) no canto inferior esquerdo.
* Retorno do resultado de cada foto processada com um **link individual de download**.
* Download individual de cada imagem finalizada em alta qualidade, diretamente pelo seu link.
* Compartilhamento da imagem processada com o Instagram pelo **menu nativo do celular** (Web Share API), permitindo escrever a legenda e concluir a publicação no feed dentro do app do Instagram.

### 2.2 O que o sistema NÃO FAZ (Out-of-Scope)
* Login/Autenticação de usuários (acesso direto e simplificado).
* Publicação automática diretamente na API do Instagram (o usuário baixa a imagem e faz a postagem).
* Troca dinâmica ou upload de logos pelo frontend (a logo é estática no backend).
* Reposicionamento manual da logo pelo usuário (o posicionamento é fixo e automático no canto inferior esquerdo).
* **Pré-visualização da imagem final na tela.** A aplicação exibe apenas o nome da foto, seu status e o link de download individual; a conferência visual é feita após o download.
* **Pré-preenchimento da legenda ou escolha forçada do destino (feed/story) no Instagram.** O site apenas abre o menu de compartilhamento do sistema; a legenda é digitada e a publicação é confirmada dentro do app do Instagram.

---

## 3. Requisitos Funcionais

| ID | Requisito | Descrição | Prioridade |
| :--- | :--- | :--- | :--- |
| **RF01** | Upload de Imagem | O sistema deve permitir o upload de uma ou várias imagens nos formatos JPG, JPEG e PNG via interface Web. | Alta |
| **RF02** | Processamento de Imagem | O backend deve ler a logo fixa da pasta `logo/` e aplicá-la com transparência/proporção adequada no canto inferior esquerdo da foto. | Alta |
| **RF03** | Resultado sem Prévia | A aplicação não deve exibir a pré-visualização da imagem final; deve listar apenas o nome do arquivo, o status do processamento e o link de download. | Média |
| **RF04** | Download do Resultado | O usuário deve conseguir baixar a imagem pronta em formato adequado para o Instagram (ex: JPG/PNG). | Alta |
| **RF05** | Limpeza de Arquivos Temporários | O servidor deve remover fotos processadas antigas periodicamente para evitar acúmulo desnecessário de disco. | Baixa |
| **RF06** | Envio em Lote | O usuário deve poder enviar quantas fotos quiser, em lote (seleção múltipla/arrastar e soltar) ou em envios sucessivos, sem limite de quantidade imposto pela interface. | Alta |
| **RF07** | Links Individuais de Download | Para cada foto processada com sucesso, o sistema deve retornar um link de download próprio, permitindo baixar cada imagem individualmente. | Alta |
| **RF08** | Compartilhar no Instagram | Em dispositivos compatíveis, o usuário deve poder compartilhar a imagem processada pelo menu nativo do sistema (Web Share API), escolher o Instagram e concluir a publicação no feed, escrevendo a legenda dentro do app. | Média |

---

## 4. Requisitos Específicos & Visão Técnica

* **Processamento de Imagem:** Utilização de bibliotecas Python de manipulação visual (ex: `Pillow / PIL` ou `OpenCV`).
* **Regra de Sobreposição (Overlay):**
  * **Posição:** Canto inferior esquerdo com margem ajustável (padding/offset) das bordas.
  * **Escala:** Redimensionamento automático da logo em relação às dimensões da imagem enviada para manter a proporção consistente.
* **Processamento em Lote:**
  * O endpoint de processamento recebe múltiplas imagens em uma única requisição (campo `files`).
  * As fotos são processadas sequencialmente para manter o consumo de memória estável.
  * Uma foto inválida gera um erro individualizado e **não interrompe** o processamento das demais.
* **Retorno sem Prévia:**
  * O backend não gera miniaturas nem imagens de pré-visualização; grava apenas a imagem final.
  * A resposta traz uma lista com o resultado de cada foto, contendo nome do arquivo, status, dimensões e o **link individual de download**.
* **Compartilhamento para o Instagram (mobile):**
  * Uso da Web Share API nível 2 (`navigator.share` com `files`), sempre disparada por um gesto do usuário e em contexto seguro (HTTPS).
  * O site entrega a imagem processada ao menu nativo do sistema; o usuário escolhe o Instagram, escreve a legenda e publica no feed pelo próprio app.
  * O download individual permanece disponível como alternativa e como **fallback** em navegadores/dispositivos sem suporte a compartilhamento de arquivos.
* **Armazenamento de Assets:** A logo será mantida no diretório backend `/logo/logo_petshop.png` (com suporte a canal Alpha/transparência).

---

## 5. Requisitos Não-Funcionais

* **Desempenho:** O tempo total de processamento e retorno de cada imagem deve ser menor que 2 segundos. Em lotes, o tempo total cresce de forma linear com a quantidade de fotos (processamento sequencial).
* **Usabilidade:** Design limpo, intuitivo e responsivo (funcional tanto em computadores de mesa quanto em celulares/tablets da equipe). O envio deve aceitar múltiplos arquivos de uma vez e a lista de resultados deve deixar claro qual link pertence a cada foto.
* **Compatibilidade:** Suporte aos principais navegadores web (Chrome, Safari, Firefox, Edge). O compartilhamento com o Instagram depende do suporte do navegador/sistema à Web Share API nível 2: em ambientes sem suporte, a aplicação deve manter o download individual como fallback.

---

## 6. Arquitetura e Tech Stack Sugerida

* **Frontend:** HTML5, CSS3 (Tailwind CSS para estilização rápida e minimalista) e JavaScript simples (Fetch API) OU Streamlit/Gradio para uma interface ágil.
* **Backend:** Python (FastAPI ou Flask).
* **Biblioteca de Imagem:** `Pillow` (PIL) para cálculo de coordenadas, transparência PNG e salvamento.
* **Estrutura de Pastas Esperada (Backend):**
  ```text
  /backend
  ├── logo/
  │   └── logo_petshop.png
  ├── app.py
  └── requirements.txt
  ```