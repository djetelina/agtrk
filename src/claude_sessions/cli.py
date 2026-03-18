import typer

app = typer.Typer()


@app.command()
def placeholder() -> None:
    typer.echo("session cli")
