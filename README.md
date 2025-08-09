# Gerenciador de Pastas

<p align="center">
<img alt="Imagem de CriptoApp" width="500px" src="https://imgur.com/YjjSYia.png">
</p>

## 📖 Sobre o Projeto

O **Gerenciador de Pastas** é uma aplicação de desktop desenvolvida em Python com uma interface gráfica feita em Tkinter. A sua principal função é automatizar a organização de arquivos em um diretório específico. Ele move os arquivos para pastas correspondentes aos seus tipos (ex: `.pdf`, `.docx`, `.jpg`), mantendo sua área de trabalho ou pasta de downloads sempre organizada.

A aplicação permite que o usuário selecione um diretório e, com um único clique, todos os arquivos nesse local são movidos para subpastas categorizadas.

## ✨ Funcionalidades

* **Interface Gráfica Simples:** Fácil de usar, com todas as opções acessíveis na janela principal.
* **Seleção de Diretório:** Permite ao usuário escolher qualquer pasta em seu sistema para organizar.
* **Organização Automática:** Move os arquivos para pastas nomeadas de acordo com suas extensões (ex: "Arquivos PDF", "Imagens", "Documentos").
* **Configuração Flexível:** As extensões de arquivo e os nomes das pastas de destino podem ser personalizados através de um arquivo `config.json`.
* **Log de Atividades:** Exibe em tempo real os arquivos que estão sendo movidos e para onde.

## 🚀 Como Usar

Para utilizar a aplicação, não é necessário instalar o Python ou qualquer dependência. Basta seguir os passos abaixo:

1.  **Baixe o Executável:**
    * Vá para a pasta `dist/` neste repositório.
    * Faça o download do arquivo `OrganizadorDeArquivos.exe`.

2.  **Execute a Aplicação:**
    * Dê um duplo clique no arquivo `OrganizadorDeArquivos.exe`.
    * A janela principal da aplicação será aberta.

3.  **Selecione a Pasta:**
    * Clique no botão **"Selecionar Pasta"**.
    * Navegue pelas suas pastas e escolha o diretório que você deseja organizar. O caminho da pasta aparecerá no campo de texto.

4.  **Inicie a Organização:**
    * Clique no botão **"Organizar Pasta"**.
    * Aguarde enquanto a aplicação move os arquivos. O progresso será exibido na área de log na parte inferior da janela.

5.  **Pronto!**
    * Seus arquivos agora estão organizados em subpastas.

## ⚙️ Configuração (Avançado)

A aplicação utiliza um arquivo `config.json` para definir quais tipos de arquivos são organizados e para quais pastas eles são movidos. Se o arquivo `config.json` não for encontrado, a aplicação criará um com as configurações padrão.

Você pode editar este arquivo para adicionar novas extensões ou alterar os nomes das pastas.

**Exemplo do `config.json`:**

```json
{
    "extensoes": {
        "Arquivos PDF": [".pdf"],
        "Imagens": [".jpg", ".jpeg", ".png", ".gif", ".bmp"],
        "Documentos": [".doc", ".docx", ".txt", ".rtf", ".odt"],
        "Planilhas": [".xls", ".xlsx", ".csv"],
        "Apresentacoes": [".ppt", ".pptx"],
        "Executaveis": [".exe", ".msi"],
        "Compactados": [".zip", ".rar", ".7z", ".tar", ".gz"],
        "Videos": [".mp4", ".mov", ".avi", ".mkv"],
        "Musicas": [".mp3", ".wav", ".flac"]
    }
}
````

Para que suas alterações tenham efeito, o arquivo `config.json` deve estar na mesma pasta que o executável `OrganizadorDeArquivos.exe`.

## 🛠️ Como Construir a Partir do Código-Fonte

Se você deseja modificar o código ou construir o executável por conta própria, siga estes passos:

1.  **Clone o repositório:**

    ```bash
    git clone [https://github.com/seu-usuario/seu-repositorio.git](https://github.com/seu-usuario/seu-repositorio.git)
    cd seu-repositorio
    ```

2.  **Crie um ambiente virtual (recomendado):**

    ```bash
    python -m venv venv
    source venv/bin/activate  # No Windows: venv\Scripts\activate
    ```

3.  **Instale as dependências:**
    Não há dependências externas além da biblioteca padrão do Python. Para criar o executável, você precisará do `pyinstaller`:

    ```bash
    pip install pyinstaller
    ```

4.  **Execute o script Python:**

    ```bash
    python organizer_app.py
    ```

5.  **Para criar o executável:**
    Use o PyInstaller para empacotar a aplicação em um único arquivo `.exe`.

    ```bash
    pyinstaller --onefile --windowed --name OrganizadorDeArquivos organizer_app.py
    ```

    O executável será criado na pasta `dist/`.

## 👤 Autor

  * **Raphael Stinson**

<!-- end list -->
