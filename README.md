"# rank_fiis" # Ranking de Fundos Imobiliários (FIIs) com Streamlit

Este projeto apresenta uma ferramenta interativa construída com Streamlit para analisar e filtrar Fundos Imobiliários (FIIs) brasileiros, utilizando dados públicos do site Fundamentus.


## 🎯 Propósito

O objetivo principal desta ferramenta é auxiliar investidores e estudantes do mercado de FIIs a:

1.  **Filtrar FIIs:** Aplicar critérios quantitativos comuns (P/VP, Dividend Yield, Liquidez) para identificar fundos que se encaixem em determinados perfis de investimento.
2.  **Ordenar por Score Personalizado:** Calcular um score baseado na importância (peso) que o próprio usuário define para diferentes indicadores (P/VP, DY, Liquidez, Vacância), permitindo uma ordenação personalizada baseada no que o usuário mais valoriza.
3.  **Visualizar Dados:** Apresentar os dados de forma organizada, com informações relevantes, links úteis e visualizações gráficas (distribuição por segmento, relação DY vs P/VP).
4.  **Facilitar a Pesquisa Inicial:** Servir como um **ponto de partida** para a análise de FIIs, agilizando a identificação de fundos que merecem uma investigação mais aprofundada através da leitura de relatórios gerenciais e outras análises qualitativas.

**⚠️ Importante:** Esta ferramenta é para fins de estudo e análise pessoal. As informações apresentadas **NÃO** constituem recomendação de compra ou venda de ativos financeiros. Faça sempre sua própria análise (DYOR - Do Your Own Research).

## ✨ Funcionalidades

*   **Interface Web Interativa:** Construída com [Streamlit](https://streamlit.io/).
*   **Coleta de Dados:** Busca dados atualizados do [Fundamentus](https://www.fundamentus.com.br/).
*   **Filtros Personalizáveis:**
    *   P/VP (Preço / Valor Patrimonial) Mínimo e Máximo.
    *   Dividend Yield (%) Mínimo e Máximo.
    *   Liquidez Mínima Diária (R$).
*   **Score Personalizado:**
    *   Defina pesos para P/VP, DY, Liquidez e Vacância.
    *   A tabela é ordenada automaticamente pelo score calculado (menor score = melhor combinação teórica).
*   **Visualização em Abas:** Resultados separados por segmento de atuação (com "Logística" agregando Imóveis Industriais).
*   **Dados Detalhados:** Exibe cotação, FFO Yield, DY, P/VP, liquidez, valor de mercado, qtd. imóveis, vacância, oscilações diária/mês/12M, data do último relatório.
*   **Links Úteis:** Links diretos para a página do FII no Fundamentus e para download do último relatório gerencial (quando disponível).
*   **Gráficos:**
    *   Distribuição de FIIs por Segmento (Gráfico de Barras).
    *   Relação Dividend Yield (%) vs P/VP (Gráfico de Dispersão Interativo).
*   **Classificação Aprimorada:** Utiliza um arquivo JSON (`fii_types.json`) para refinar a classificação por Segmento e adicionar a coluna "Tipo" (Tijolo, Papel, Híbrido, etc.).
*   **Download:** Opção para baixar a tabela completa (incluindo ranks individuais e score) em formato Excel (.xlsx).
*   **Seção de Ajuda:** Explicações sobre os indicadores e o uso da ferramenta.

## 🛠️ Como Usar (Localmente)

1.  **Clone o Repositório:**
    ```bash
    git clone https://github.com/guteco/rank_fiis.git
    cd rank_fiis
    ```
2.  **Crie e Ative um Ambiente Virtual:**
    ```bash
    python -m venv venv
    # Windows
    .\venv\Scripts\activate
    # macOS/Linux
    source venv/bin/activate
    ```
3.  **Instale as Dependências:**
    ```bash
    pip install -r requirements.txt
    ```
4.  **Execute o Aplicativo Streamlit:**
    ```bash
    streamlit run app.py
    ```
5.  Abra o navegador no endereço local fornecido (geralmente `http://localhost:8501`).

## 📂 Estrutura do Projeto

*   `app.py`: Script principal da aplicação Streamlit (interface web).
*   `rank_fiis.py`: Módulo contendo a lógica de coleta, processamento e cálculo dos dados dos FIIs.
*   `fii_types.json`: Arquivo JSON com classificação manual de Segmento e Tipo para os FIIs.
*   `fii_template.html`: Template Jinja2 usado para renderizar a tabela HTML na interface.
*   `requirements.txt`: Lista de dependências Python.
*   `.streamlit/config.toml`: Arquivo de configuração do Streamlit (força o tema escuro).
*   `README.md`: Este arquivo.

## 🙏 Créditos e Agradecimentos

*   **Desenvolvimento:** Augusto Severo ([@guteco](https://www.instagram.com/guteco/))
*   **Assistência e Código Base:** IA do Google (Gemini)
*   **Fonte dos Dados:** [Fundamentus](https://www.fundamentus.com.br/)
*   **Motivação:** A busca incessante por conhecimento e uma boa pizza! 🍕

## 📧 Contato

Encontrou algum bug, classificação incorreta ou tem sugestões? Entre em contato: `contato@nerdpobre.com`

---

*Este projeto é fornecido "como está", sem garantias. Use por sua conta e risco.*