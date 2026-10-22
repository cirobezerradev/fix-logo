# Documento de Requisitos do Produto (PRD)

## 1. Visão Geral do Produto

* **Nome do Projeto:** PetShop Watermark Automator
* **Objetivo:** Automatizar a aplicação da logomarca do petshop no canto inferior esquerdo das fotos dos animais de estimação, eliminando o processo manual de edição para publicação no feed do Instagram.
* **Público-Alvo:** Funcionários e equipe de marketing do petshop.

---

## 2. Escopo do Sistema

### 2.1 O que o sistema FAZ (In-Scope)
* Interface web minimalista e responsiva para upload de imagem pelo usuário.
* Envio da foto original para o backend em Python.
* Processamento da imagem no backend inserindo a logo fixa (armazenada localmente na pasta `logo/`) no canto inferior esquerdo.
* Previsualização da imagem final já com a logo sobreposta.
* Botão para download direto da imagem finalizada em alta qualidade.

### 2.2 O que o sistema NÃO FAZ (Out-of-Scope)
* Login/Autenticação de usuários (acesso direto e simplificado).
* Publicação automática diretamente na API do Instagram (o usuário baixa a imagem e faz a postagem).
* Troca dinâmica ou upload de logos pelo frontend (a logo é estática no backend).
* Reposicionamento manual da logo pelo usuário (o posicionamento é fixo e automático no canto inferior esquerdo).

---

## 3. Requisitos Funcionais

| ID | Requisito | Descrição | Prioridade |
| :--- | :--- | :--- | :--- |
| **RF01** | Upload de Imagem | O sistema deve permitir o upload de imagens nos formatos JPG, JPEG e PNG via interface Web. | Alta |
| **RF02** | Processamento de Imagem | O backend deve ler a logo fixa da pasta `logo/` e aplicá-la com transparência/proporção adequada no canto inferior esquerdo da foto. | Alta |
| **RF03** | Visualização Prévia | A aplicação web deve exibir o resultado da imagem processada antes do download. | Média |
| **RF04** | Download do Resultado | O usuário deve conseguir baixar a imagem pronta em formato adequado para o Instagram (ex: JPG/PNG). | Alta |
| **RF05** | Limpeza de Arquivos Temporários | O servidor deve remover fotos processadas antigas periodicamente para evitar acúmulo desnecessário de disco. | Baixa |

---

## 4. Requisitos Específicos & Visão Técnica

* **Processamento de Imagem:** Utilização de bibliotecas Python de manipulação visual (ex: `Pillow / PIL` ou `OpenCV`).
* **Regra de Sobreposição (Overlay):**
  * **Posição:** Canto inferior esquerdo com margem ajustável (padding/offset) das bordas.
  * **Escala:** Redimensionamento automático da logo em relação às dimensões da imagem enviada para manter a proporção consistente.
* **Armazenamento de Assets:** A logo será mantida no diretório backend `/logo/logo_petshop.png` (com suporte a canal Alpha/transparência).

---

## 5. Requisitos Não-Funcionais

* **Desempenho:** O tempo total de processamento e retorno da imagem deve ser menor que 2 segundos.
* **Usabilidade:** Design limpo, intuitivo e responsivo (funcional tanto em computadores de mesa quanto em celulares/tablets da equipe).
* **Compatibilidade:** Suporte aos principais navegadores web (Chrome, Safari, Firefox, Edge).

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