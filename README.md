<div align="center">

# Gerenciador de Emuladores

Launcher para Windows que organiza seus emuladores e jogos, baixa tudo sob demanda e abre cada jogo no emulador certo.

[![Último release](https://img.shields.io/github/v/release/igordssrosa/gerenciador-de-emuladores?style=flat-square&color=7B1E3A&label=release&cacheSeconds=3600)](https://github.com/igordssrosa/gerenciador-de-emuladores/releases/latest)
[![Downloads](https://img.shields.io/github/downloads/igordssrosa/gerenciador-de-emuladores/total?style=flat-square&color=2250C4&cacheSeconds=3600)](https://github.com/igordssrosa/gerenciador-de-emuladores/releases)
![Plataforma](https://img.shields.io/badge/plataforma-Windows%2010%20%7C%2011-2250C4?style=flat-square)

[**Baixar**](https://github.com/igordssrosa/gerenciador-de-emuladores/releases/latest) · [Instalação](#instalação) · [Atualizar](#atualizar)

<img src="docs/home-v2.png" alt="Tela inicial, com menu lateral e um bloco por emulador" width="780">

</div>

## Visão geral

O Gerenciador de Emuladores reúne em uma única janela os emuladores e os jogos de cada um. Nada é baixado até você pedir: com um clique em **Baixar**, o app obtém o emulador e o jogo, e com **Jogar** abre o título no emulador correto, já configurado.

| Recurso                       | Descrição                                                                                           |
| ----------------------------- | --------------------------------------------------------------------------------------------------- |
| **Download sob demanda**      | Emuladores e jogos são baixados quando você pede, com barra de progresso e cancelamento.            |
| **Save states**               | Lista os save states do emulador, do mais recente ao mais antigo, para carregar e jogar ou excluir. |
| **Saves do jogo**             | Importa e exporta o `.sav` de cada jogo.                                                            |
| **Biblioteca**                | Jogos em blocos ou em lista, com capas, filtros (todos, prontos, não baixados) e busca por nome.    |
| **Tema claro e escuro**       | Segue o tema do Windows e pode ser trocado pelo menu lateral.                                       |
| **Uso offline**               | Mantém uma cópia local da lista de jogos e usa o que já foi baixado.                                |
| **Atualização com um clique** | Avisa quando há versão nova e atualiza sem sair do app.                                             |
| **Sem dependências**          | Instalador por usuário, sem privilégios de administrador e sem precisar de Python.                  |

<div align="center">
<img src="docs/jogos-v2.png" alt="Biblioteca de um emulador no tema claro, com um download em andamento" width="48%">
<img src="docs/saves-v2.png" alt="Tela do jogo no tema escuro, com a lista de save states e o save atual" width="48%">
</div>

## Instalação

**Requisitos:** Windows 10 ou 11 e conexão com a internet para os downloads.

1. Baixe o `Instalar-GerenciadorEmuladores-X.Y.Z.exe` na página de [Releases](https://github.com/igordssrosa/gerenciador-de-emuladores/releases/latest).
2. Execute o instalador. Ele instala apenas para o seu usuário e não pede senha de administrador.
3. Abra o app pelo atalho da área de trabalho ou do menu Iniciar.

Também há o `GerenciadorEmuladores.exe` avulso, que roda sem instalação.

<details>
<summary><b>O Windows exibiu "O Windows protegeu seu PC"</b></summary>

<br>

O aviso do SmartScreen aparece para programas novos que não possuem assinatura digital. Clique em **Mais informações** e depois em **Executar assim mesmo**. Todo o código-fonte está neste repositório para consulta.

</details>

<details>
<summary><b>O app pediu para instalar o WebView2</b></summary>

<br>

A interface usa o Microsoft Edge WebView2, componente gratuito que já acompanha o Windows 11 e a maioria dos Windows 10. Se estiver ausente, o app oferece baixá-lo e instalá-lo na primeira abertura.

</details>

<details>
<summary><b>Alguma capa ou download não aparece</b></summary>

<br>

Confira se há conexão com a internet e use **Atualizar catálogo** no menu lateral para baixar a lista de jogos de novo.

</details>

## Atualizar

Quando existe uma versão nova, aparece o botão **Nova versão** no menu lateral. Ao clicar e confirmar, o app baixa a atualização, fecha, instala por cima e abre de novo sozinho. Seus jogos, saves e save states não são mexidos.

Se houver um jogo aberto no emulador, o app pede para fechá-lo antes de atualizar. Se preferir, instale a versão nova manualmente: basta rodar o `Instalar-GerenciadorEmuladores-X.Y.Z.exe` por cima do atual.

## Seus dados

Jogos, emuladores, saves e save states ficam em `%LOCALAPPDATA%\GerenciadorEmuladores\`, fora de pastas sincronizadas como o OneDrive, para evitar que um `.sav` seja sincronizado enquanto o emulador escreve nele. Desinstalar o app remove só o programa: seus jogos e saves permanecem nessa pasta e podem ser apagados manualmente.

> [!NOTE]
> Este projeto não inclui nem distribui ROMs ou BIOS. Use apenas conteúdo que você tem direito de utilizar.
