from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="home"),
    path("scrum/projecte", views.index, name="projectes"),
    path("scrum/projectes", views.index, name="projectes2"),
    path("scrum/projecte/<int:id>", views.projecte, name="projecte"),
    path("scrum/qualifica", views.qualifica, name="qualifica"),
    path(
        "scrum/descarrega_qualificacions/<int:projecte_id>",
        views.descarrega_qualificacions,
        name="descarrega_qualificacions",
    ),
    # API
    path(
        "scrum/api/crea_qualificacio/<int:sprint_id>/<int:equip_id>",
        views.crea_qualificacio,
        name="crea_qualificacio",
    ),
    path(
        "scrum/api/elimina_qualificacio/<int:qualificacio_id>",
        views.elimina_qualificacio,
        name="elimina_qualificacio",
    ),
    path(
        "scrum/api/get_done_specs/<int:qualificacio_id>",
        views.get_done_specs,
        name="get_done_specs",
    ),
    path(
        "scrum/api/get_qualificacio/<int:qualificacio_id>",
        views.get_qualificacio,
        name="get_qualificacio",
    ),
    path(
        "scrum/api/toggle_done_spec/<int:done_spec_id>",
        views.toggle_done_spec,
        name="toggle_done_spec",
    ),
    path(
        "scrum/api/set_comment_to_qualificacio/<int:qualificacio_id>",
        views.set_comment_to_qualificacio,
        name="set_comment_to_qualificacio",
    ),
]
