from django import forms

from .models import Note, Task


class TaskForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = ["title", "description", "status", "priority", "due_date"]
        widgets = {
            "title": forms.TextInput(attrs={"placeholder": "What needs to get done?", "autofocus": True}),
            "description": forms.Textarea(attrs={"rows": 5, "placeholder": "Details, links, context (optional)"}),
            "due_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }


class NoteForm(forms.ModelForm):
    class Meta:
        model = Note
        fields = ["title", "body", "task"]
        labels = {"task": "Linked task"}
        widgets = {
            "title": forms.TextInput(attrs={"placeholder": "Note title", "autofocus": True}),
            "body": forms.Textarea(attrs={"rows": 8, "placeholder": "Write your note"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        # A note can only be linked to the current user's own tasks.
        qs = Task.objects.filter(owner=user) if user else Task.objects.none()
        self.fields["task"].queryset = qs
        self.fields["task"].empty_label = "No linked task"
