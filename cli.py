#!/usr/bin/env python3
import sys
import os
import time
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.table import Table
from rich.prompt import Prompt
from rich.live import Live
from rich.spinner import Spinner
from rich.text import Text

from chatgpt_client import ChatGPTClient

console = Console()
client = ChatGPTClient()

def print_banner():
    banner = Panel.fit(
        "[bold cyan]🤖 ChatGPT Terminal (Console CLI Client)[/bold cyan]\n"
        "[dim]HAR İncelemesi Esas Alınarak Hazırlanmıştır[/dim]\n\n"
        "[yellow]Komutlar:[/yellow]\n"
        "  [green]/auth[/green]       - Cookie veya Session Auth Token tanımla/güncelle\n"
        "  [green]/list[/green]       - Geçmiş sohbetleri listele\n"
        "  [green]/load <id>[/green]  - Geçmiş bir sohbeti yükle\n"
        "  [green]/new[/green]        - Yeni sohbet başlat\n"
        "  [green]/model[/green]      - Model değiştir (auto, gpt-4o, gpt-4o-mini...)\n"
        "  [green]/status[/green]     - Mevcut oturum durumunu göster\n"
        "  [green]/help[/green]       - Yardım menüsünü göster\n"
        "  [green]/exit[/green]       - Çıkış yap",
        border_style="cyan"
    )
    console.print(banner)

def check_auth():
    cfg = client.config
    has_auth = bool(cfg.get("cookie", "").strip() or cfg.get("auth_token", "").strip())
    if not has_auth:
        console.print("\n[bold red]⚠️ Giriş Bilgisi Eksik![/bold red]")
        console.print("[yellow]ChatGPT hesabınıza erişmek için Cookie veya Session Auth Token gereklidir.[/yellow]")
        console.print("Tarayıcınızın DevTools (F12) -> Network kısmından kopyaladığınız Cookie metnini veya [blue]https://chatgpt.com/api/auth/session[/blue] sayfasındaki Access Token'ı girebilirsiniz.\n")
        set_auth_prompt()

def set_auth_prompt():
    console.print("[bold cyan]=== Oturum / Yetkilendirme Ayarları ===[/bold cyan]")
    auth_choice = Prompt.ask("Hangisini girmek istersiniz?", choices=["cookie", "token", "skip"], default="cookie")
    
    if auth_choice == "cookie":
        raw_cookie = Prompt.ask("Lütfen tam Cookie dizgisini yapıştırın")
        if raw_cookie.strip():
            client.update_settings(cookie=raw_cookie)
            console.print("[bold green]✅ Cookie başarıyla kaydedildi![/bold green]\n")
    elif auth_choice == "token":
        token_str = Prompt.ask("Lütfen Authorization Bearer / Session Token yapıştırın")
        if token_str.strip():
            client.update_settings(auth_token=token_str)
            console.print("[bold green]✅ Auth Token başarıyla kaydedildi![/bold green]\n")
    elif auth_choice == "skip":
        console.print("[dim]Atlandı. Daha sonra /auth komutu ile girebilirsiniz.[/dim]\n")

def show_status():
    cfg = client.config
    table = Table(title="Mevcut Yapılandırma & Oturum Durumu", show_header=True, header_style="bold magenta")
    table.add_column("Parametre", style="cyan")
    table.add_column("Değer", style="white")

    has_cookie = bool(cfg.get("cookie", "").strip())
    has_auth = bool(cfg.get("auth_token", "").strip())

    table.add_row("Cookie Durumu", "[green]Kayıtlı[/green]" if has_cookie else "[red]Yok[/red]")
    table.add_row("Auth Token Durumu", "[green]Kayıtlı[/green]" if has_auth else "[red]Yok[/red]")
    table.add_row("Model", cfg.get("model", "auto"))
    table.add_row("Device ID", cfg.get("oai_device_id", ""))
    table.add_row("Timezone", cfg.get("timezone", ""))

    console.print(table)

def show_conversations():
    console.print("[cyan]Sohbetler getiriliyor...[/cyan]")
    try:
        data = client.list_conversations()
        items = data.get("items", [])
        if not items:
            console.print("[yellow]Geçmiş sohbet bulunamadı.[/yellow]")
            return

        table = Table(title="Son ChatGPT Sohbetleri", show_header=True, header_style="bold green")
        table.add_column("#", style="dim", width=4)
        table.add_column("Sohbet ID", style="cyan")
        table.add_column("Başlık", style="bold white")
        table.add_column("Güncellenme Tarihi", style="dim")

        for idx, item in enumerate(items[:15], 1):
            cid = item.get("id", "")
            title = item.get("title", "İsimsiz Sohbet")
            updated = item.get("update_time", "")[:19].replace("T", " ")
            table.add_row(str(idx), cid, title, updated)

        console.print(table)
        console.print("[dim]Bir sohbeti açmak için: /load <Sohbet ID>[/dim]\n")
    except Exception as e:
        console.print(f"[bold red]Hata:[/bold red] {e}")

def main():
    print_banner()
    check_auth()

    current_conv_id = None
    current_parent_id = None

    while True:
        try:
            prompt_label = "[bold green]ChatGPT[/bold green]"
            if current_conv_id:
                prompt_label += f" [dim]({current_conv_id[:8]}...)[/dim]"
            
            user_input = console.input(f"\n{prompt_label} > ").strip()
            if not user_input:
                continue

            if user_input.startswith("/"):
                parts = user_input.split(maxsplit=1)
                cmd = parts[0].lower()
                arg = parts[1] if len(parts) > 1 else ""

                if cmd in ["/exit", "/quit"]:
                    console.print("[cyan]Görüşmek üzere![/cyan]")
                    sys.exit(0)
                elif cmd == "/auth":
                    set_auth_prompt()
                elif cmd == "/status":
                    show_status()
                elif cmd == "/list":
                    show_conversations()
                elif cmd == "/new":
                    current_conv_id = None
                    current_parent_id = None
                    console.print("[bold green]✨ Yeni sohbet başlatıldı![/bold green]")
                elif cmd == "/load":
                    if not arg:
                        console.print("[yellow]Kullanım: /load <Sohbet ID>[/yellow]")
                    else:
                        current_conv_id = arg.strip()
                        console.print(f"[bold green]Sohbet yüklendi: {current_conv_id}[/bold green]")
                elif cmd == "/model":
                    if not arg:
                        m = Prompt.ask("Model seçin", choices=["auto", "gpt-4o", "gpt-4o-mini", "gpt-4"], default=client.config.get("model", "auto"))
                        client.update_settings(model=m)
                    else:
                        client.update_settings(model=arg.strip())
                    console.print(f"[bold green]Model değiştirildi: {client.config.get('model')}[/bold green]")
                elif cmd == "/help":
                    print_banner()
                else:
                    console.print(f"[red]Bilinmeyen komut: {cmd}. Menü için /help yazabilirsiniz.[/red]")
                continue

            # Send prompt to ChatGPT
            full_text = ""
            spinner_text = Text("ChatGPT yanıt veriyor...", style="cyan")

            with Live(Spinner("dots", text=spinner_text), console=console, refresh_per_second=10) as live:
                for chunk in client.send_message_stream(user_input, conversation_id=current_conv_id, parent_message_id=current_parent_id):
                    ctype = chunk.get("type")

                    if ctype == "error":
                        live.update(Panel(f"[bold red]Hata:[/bold red] {chunk.get('content')}", border_style="red"))
                        full_text = None
                        break
                    elif ctype == "text":
                        full_text = chunk.get("full_text", "")
                        if chunk.get("conversation_id"):
                            current_conv_id = chunk.get("conversation_id")
                        if chunk.get("message_id"):
                            current_parent_id = chunk.get("message_id")

                        md = Markdown(full_text)
                        live.update(Panel(md, title="[bold green]ChatGPT[/bold green]", border_style="green"))
                    elif ctype == "done":
                        if chunk.get("conversation_id"):
                            current_conv_id = chunk.get("conversation_id")
                        if chunk.get("message_id"):
                            current_parent_id = chunk.get("message_id")

            if full_text:
                console.print()

        except KeyboardInterrupt:
            console.print("\n[yellow]İşlem iptal edildi.[/yellow]")
        except Exception as e:
            console.print(f"\n[bold red]Beklenmeyen hata:[/bold red] {e}")

if __name__ == "__main__":
    main()
