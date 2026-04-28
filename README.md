# Anime Monitor

App desktop para monitorar e baixar automaticamente novos episódios de anime via torrent. Gerencia sua lista, busca metadados do MyAnimeList e organiza os arquivos automaticamente.

## Funcionalidades

- Monitorar múltiplas séries simultaneamente
- Detectar automaticamente novos episódios via RSS do SubsPlease
- Disparar downloads via magnet link automaticamente
- Buscar e exibir metadados (capa, status, sinopse) do MyAnimeList
- Download de legendas pelo AnimeTosho
- Organizar arquivos baixados para a pasta de episódios automaticamente
- Ícone na bandeja do sistema com notificações
- Importar/exportar lista de animes
- Atualização automática do app

## Requisitos

- Python 3.11+
- `tkinter` (geralmente incluso; no Linux: `sudo apt install python3-tk`)
- Um cliente BitTorrent com suporte a magnet links (ex: qBittorrent)

## Instalação

```bash
git clone https://github.com/kahd0/animedownloader.git
cd animedownloader
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Executando

```bash
source .venv/bin/activate
PYTHONPATH=. python3 main.py
```

## Estrutura do Projeto

```
app/
  core/       # Config, banco de dados, APIs, lógica de download
  ui/         # Interface tkinter (janela principal, diálogos, componentes)
  utils/      # Bridge async, atualizador, parser de episódios
episodes/     # Destino final dos arquivos de vídeo baixados
legendas/     # Pasta temporária para legendas baixadas
covers/       # Capas dos animes (baixadas em tempo de execução)
```

## Configuração

Na primeira execução, abra **Configurações** para definir:

- **Pasta de episódios** — onde os vídeos organizados são salvos
- **Pasta de legendas** — pasta temporária para arquivos `.ass`
- **Intervalo de verificação** — frequência para checar novos episódios (minutos)
- **Organizar automaticamente** — mover torrents concluídos para a pasta de episódios
