from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="home"),
    path("scrum/projecte", views.index, name="projectes"),
    path("scrum/projectes", views.index, name="projectes2"),
    path("scrum/projecte/<int:id>", views.projecte, name="projecte"),
    path(
        "scrum/projectes/<int:id>/clona",
        views.clona_projecte,
        name="clona_projecte",
    ),
    path("scrum/qualifica", views.qualifica, name="qualifica"),
    path("scrum/perfil", views.perfil, name="perfil"),
    path("scrum/api/cerca_centres", views.cerca_centres, name="cerca_centres"),
    path("scrum/api/cerca_cicles", views.cerca_cicles, name="cerca_cicles"),
    path("scrum/api/cerca_moduls", views.cerca_moduls, name="cerca_moduls"),
    path("scrum/api/cerca_sprints", views.cerca_sprints, name="cerca_sprints"),
    path(
        "scrum/els-meus-projectes",
        views.els_meus_projectes,
        name="els_meus_projectes",
    ),
    path(
        "scrum/els-meus-projectes/nou",
        views.crea_projecte,
        name="crea_projecte",
    ),
    path(
        "scrum/els-meus-projectes/<int:id>/edita",
        views.edita_projecte,
        name="edita_projecte",
    ),
    path(
        "scrum/els-meus-projectes/<int:id>/elimina",
        views.elimina_projecte,
        name="elimina_projecte",
    ),
    path(
        "scrum/els-meus-projectes/<int:projecte_id>/qualifica",
        views.qualifica_projecte,
        name="qualifica_projecte",
    ),
    path(
        "scrum/els-meus-projectes/<int:projecte_id>/specs/nou",
        views.crea_spec,
        name="crea_spec",
    ),
    path(
        "scrum/els-meus-projectes/<int:projecte_id>/specs/reordena",
        views.reordena_specs,
        name="reordena_specs",
    ),
    path(
        "scrum/specs/<int:id>/actualitza",
        views.actualitza_spec,
        name="actualitza_spec",
    ),
    path(
        "scrum/specs/<int:id>/hores",
        views.actualitza_hores_spec,
        name="actualitza_hores_spec",
    ),
    path(
        "scrum/els-meus-projectes/<int:projecte_id>/sprints/nou",
        views.crea_sprint,
        name="crea_sprint",
    ),
    path(
        "scrum/sprints/<int:id>/edita",
        views.edita_sprint,
        name="edita_sprint",
    ),
    path("scrum/videos", views.videos, name="videos"),
    path("scrum/equips", views.els_meus_equips, name="els_meus_equips"),
    path("scrum/equips/nou", views.crea_equip, name="crea_equip"),
    path(
        "scrum/equips/<int:id>/edita",
        views.edita_equip,
        name="edita_equip",
    ),
    path("scrum/api/cerca_usuaris", views.cerca_usuaris, name="cerca_usuaris"),
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
        "scrum/api/set_percentatge_done_spec/<int:done_spec_id>",
        views.set_percentatge_done_spec,
        name="set_percentatge_done_spec",
    ),
    path(
        "scrum/api/set_percentatges_done_spec_mp/<int:done_spec_id>",
        views.set_percentatges_done_spec_mp,
        name="set_percentatges_done_spec_mp",
    ),
    path(
        "scrum/api/set_comment_to_qualificacio/<int:qualificacio_id>",
        views.set_comment_to_qualificacio,
        name="set_comment_to_qualificacio",
    ),
]
