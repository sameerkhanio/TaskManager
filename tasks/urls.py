from django.urls import path

from . import views

urlpatterns = [
    path("", views.DashboardView.as_view(), name="dashboard"),
    path("signup/", views.SignUpView.as_view(), name="signup"),
    path("board/", views.BoardView.as_view(), name="board"),
    path("tasks/", views.TaskListView.as_view(), name="task_list"),
    path("tasks/new/", views.TaskCreateView.as_view(), name="task_create"),
    path("tasks/<int:pk>/edit/", views.TaskUpdateView.as_view(), name="task_update"),
    path("tasks/<int:pk>/delete/", views.TaskDeleteView.as_view(), name="task_delete"),
    path("tasks/<int:pk>/move/", views.TaskMoveView.as_view(), name="task_move"),
    path("notes/", views.NoteListView.as_view(), name="note_list"),
    path("notes/new/", views.NoteCreateView.as_view(), name="note_create"),
    path("notes/<int:pk>/edit/", views.NoteUpdateView.as_view(), name="note_update"),
    path("notes/<int:pk>/delete/", views.NoteDeleteView.as_view(), name="note_delete"),
]
