from django import forms

from .models import Projecte, Spec
from .widgets import Base64CKEditor5Widget


class ProjecteDescripcioForm(forms.ModelForm):
    class Meta:
        model = Projecte
        fields = ["descripcio"]
        widgets = {"descripcio": Base64CKEditor5Widget()}


class SpecDescripcioForm(forms.ModelForm):
    class Meta:
        model = Spec
        fields = ["descripcio"]
        widgets = {"descripcio": Base64CKEditor5Widget()}
