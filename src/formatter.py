"""Rich-based output formatter for CLI results."""
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box
from src.models.match_result import MatchResult
from src.engine.confidence import MatchStatus

console = Console()

STATUS_STYLE = {
    MatchStatus.ELIGIBLE: "[bold green]✅ ELIGIBLE[/bold green]",
    MatchStatus.LIKELY_ELIGIBLE: "[bold yellow]🟡 LIKELY[/bold yellow]",
    MatchStatus.AMBIGUOUS: "[bold orange1]🟠 AMBIGUOUS[/bold orange1]",
    MatchStatus.INELIGIBLE: "[bold red]❌ INELIGIBLE[/bold red]",
    MatchStatus.INSUFFICIENT_DATA: "[dim]❓ INSUFFICIENT DATA[/dim]",
}


def format_results_table(results: list[MatchResult]) -> None:
    """Print a rich table of scheme match results."""
    table = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan")
    table.add_column("Scheme", style="bold", min_width=20)
    table.add_column("Status", min_width=18)
    table.add_column("Score", justify="right", min_width=7)
    table.add_column("Key Notes", min_width=30)

    for r in sorted(results, key=lambda x: x.confidence, reverse=True):
        notes = "; ".join(g.description[:50] for g in r.gaps[:2]) if r.gaps else r.benefit_summary[:50]
        table.add_row(
            r.scheme_name,
            STATUS_STYLE.get(r.status, str(r.status)),
            f"{r.confidence:.0f}%",
            notes,
        )
    console.print(table)


def format_gaps(result: MatchResult) -> None:
    """Print gap analysis for a scheme."""
    if not result.gaps:
        return
    gap_text = "\n".join(f"  • [{g.gap_type}] {g.description}" for g in result.gaps)
    console.print(Panel(gap_text, title=f"[yellow]Gaps for {result.scheme_name}[/yellow]", border_style="yellow"))


def format_application_order(ordered_scheme_ids: list[str]) -> None:
    """Print the recommended application order."""
    if not ordered_scheme_ids:
        return
    lines = [f"  {i+1}. {sid}" for i, sid in enumerate(ordered_scheme_ids)]
    console.print(Panel("\n".join(lines), title="[cyan]📋 Recommended Application Order[/cyan]", border_style="cyan"))
