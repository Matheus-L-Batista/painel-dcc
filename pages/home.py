import dash
from dash import html

dash.register_page(
    __name__,
    path="/",
    name="Início",
)

layout = html.Div(
    className="home-container",
    children=[
        html.Img(
            src="/assets/Painel DCC.png",
            className="home-image"
        )
    ]
)
