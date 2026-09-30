from django.contrib import admin

from .models import Note, Task


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ("title", "owner", "status", "priority", "due_date")
    list_filter = ("status", "priority")
    search_fields = ("title", "description")


@admin.register(Note)
class NoteAdmin(admin.ModelAdmin):
    list_display = ("title", "owner", "task", "updated_at")
    search_fields = ("title", "body")
