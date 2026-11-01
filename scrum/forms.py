from django import forms

from .models import Projecte, Spec


class ProjecteDescripcioForm(forms.ModelForm):
    class Meta:
        model = Projecte
        fields = ["descripcio"]


class SpecDescripcioForm(forms.ModelForm):
    class Meta:
        model = Spec
        fields = ["descripcio"]
