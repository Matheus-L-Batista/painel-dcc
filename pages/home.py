import dash
from dash import html

dash.register_page(
    __name__,
    path="/",
    name="Home"
)

layout = html.Div(
    className="home-container",
    children=[
        html.Div(className="home-overlay")
    ]
)