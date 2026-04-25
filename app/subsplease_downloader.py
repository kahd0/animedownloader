import asyncio
from datetime import datetime
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, DataTable, Input, RichLog, Label, Button
from textual.containers import Vertical, Horizontal, Container
from textual import work
from database import init_db, get_monitored_animes, add_anime, remove_anime
from downloader import check_for_updates, search_anime_history, process_releases, organize_downloads, force_download_subs

class SubsPleaseApp(App):
    CSS = """
    Screen {
        background: #121212;
    }

    #main_container {
        padding: 1;
    }

    DataTable {
        height: 60%;
        border: solid #333;
        margin-bottom: 1;
    }

    RichLog {
        height: 30%;
        border: solid #333;
        background: #000;
        scrollbar-gutter: stable;
    }

    .input_container {
        height: auto;
        margin-bottom: 1;
        padding: 1;
        border: solid #444;
    }

    Input {
        width: 60%;
    }

    #add_btn {
        width: 20%;
        margin-left: 2;
    }

    Label {
        color: #888;
        margin-bottom: 1;
    }
    """

    BINDINGS = [
        ("q", "quit", "Sair"),
        ("r", "refresh", "Verificar Agora"),
        ("d", "delete_selected", "Remover Selecionado"),
        ("o", "organize", "Organizar Pasta"),
        ("l", "download_subs", "Buscar Legendas"),
    ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Container(id="main_container"):
            yield Label("Monitoramento de Animes (SubsPlease)")
            yield DataTable(zebra_stripes=True)
            
            with Horizontal(classes="input_container"):
                yield Input(placeholder="Nome do Anime ou Nome:Ep (ex: One Piece:1100)", id="anime_input")
                yield Button("Adicionar", variant="success", id="add_btn")
            
            yield Label("Logs de Atividade")
            # Ativando auto_scroll para que mostre sempre o mais novo
            yield RichLog(highlight=True, markup=True, auto_scroll=True)
        yield Footer()

    async def on_mount(self) -> None:
        await init_db()
        table = self.query_one(DataTable)
        table.add_columns("ID", "Anime", "Último Ep", "Resolução")
        table.cursor_type = "row"
        
        await self.refresh_table()
        self.log_message("Sistema iniciado. Verificando a cada 10 minutos.")
        
        # Inicia a verificação periódica
        self.set_interval(600, self.action_refresh)
        
        # Primeira verificação imediata
        self.action_refresh()

    async def refresh_table(self):
        table = self.query_one(DataTable)
        table.clear()
        animes = await get_monitored_animes()
        for anime in animes:
            table.add_row(*[str(x) for x in anime], key=str(anime[0]))

    def log_message(self, message: str, color: str = "white"):
        log = self.query_one(RichLog)
        timestamp = datetime.now().strftime("%H:%M:%S")
        log.write(f"[{timestamp}] [{color}]{message}[/]")

    async def run_organization_logic(self):
        """Lógica interna de organização (não-worker)"""
        self.log_message("Organizando arquivos finalizados...", "blue")
        try:
            moved = await organize_downloads()
            if moved:
                for f in moved:
                    self.log_message(f"ORGANIZADO: {f}", "cyan")
            else:
                self.log_message("Nada pendente para organizar.", "yellow")
        except Exception as e:
            self.log_message(f"Erro ao organizar: {e}", "red")

    @work(exclusive=True)
    async def action_refresh(self) -> None:
        self.log_message("Verificando novas releases...", "blue")
        try:
            # 1. Verifica novos episódios
            triggered = await check_for_updates()
            if triggered:
                for item in triggered:
                    self.log_message(f"DOWNLOAD INICIADO: {item}", "green")
                await self.refresh_table()
            else:
                self.log_message("Nenhuma release nova encontrada.", "yellow")
            
            # 2. Organiza a pasta
            await self.run_organization_logic()
            
        except Exception as e:
            self.log_message(f"Erro na verificação: {e}", "red")

    @work(exclusive=True)
    async def action_organize(self) -> None:
        await self.run_organization_logic()

    @work(exclusive=True)
    async def action_download_subs(self) -> None:
        self.log_message("Buscando legendas para os episódios atuais...", "blue")
        try:
            downloaded = await force_download_subs()
            if downloaded:
                for item in downloaded:
                    self.log_message(f"LEGENDA BAIXADA: {item}", "green")
                # Tenta organizar logo em seguida
                await self.run_organization_logic()
            else:
                self.log_message("Nenhuma legenda nova encontrada.", "yellow")
        except Exception as e:
            self.log_message(f"Erro ao buscar legendas: {e}", "red")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "add_btn":
            await self.add_current_anime()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "anime_input":
            await self.add_current_anime()

    async def add_current_anime(self):
        input_widget = self.query_one("#anime_input", Input)
        raw_value = input_widget.value.strip()
        
        if ":" in raw_value:
            parts = raw_value.rsplit(":", 1)
            name = parts[0].strip()
            try:
                start_ep = int(parts[1].strip())
            except ValueError:
                start_ep = 0
        else:
            name = raw_value
            start_ep = 0

        if name:
            success = await add_anime(name, start_episode=start_ep)
            if success:
                self.log_message(f"Adicionado: {name} (Iniciando após Ep {start_ep})", "cyan")
                input_widget.value = ""
                await self.refresh_table()
                
                # BUSCA PROFUNDA
                self.log_message(f"Buscando histórico completo de '{name}'...", "blue")
                history = await search_anime_history(name)
                if history:
                    triggered = await process_releases(history)
                    if triggered:
                        for item in triggered:
                            self.log_message(f"DOWNLOAD HISTÓRICO: {item}", "green")
                        await self.refresh_table()
                    else:
                        self.log_message("Nenhum episódio novo encontrado no histórico.", "yellow")
                else:
                    self.log_message("Histórico não encontrado. Verificando feed geral...", "yellow")
                    await self.action_refresh()
            else:
                self.log_message(f"Erro: {name} já está na lista ou erro no banco.", "red")

    async def action_delete_selected(self) -> None:
        table = self.query_one(DataTable)
        try:
            row_key = table.coordinate_to_cell_key(table.cursor_coordinate).row_key
            anime_id = int(row_key.value)
            await remove_anime(anime_id)
            self.log_message(f"Anime ID {anime_id} removido.", "orange")
            await self.refresh_table()
        except Exception:
            self.log_message("Nenhum anime selecionado para remover.", "red")

if __name__ == "__main__":
    app = SubsPleaseApp()
    app.run()
