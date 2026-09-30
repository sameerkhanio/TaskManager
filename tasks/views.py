from datetime import timedelta

from django.contrib.auth import login
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import Case, Count, F, IntegerField, Q, When
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.generic import CreateView, DeleteView, ListView, TemplateView, UpdateView

from .forms import NoteForm, TaskForm
from .models import Note, Task


class OwnedMixin(LoginRequiredMixin):
    """Every query is limited to the logged-in user's own rows."""

    def get_queryset(self):
        return super().get_queryset().filter(owner=self.request.user)


# --- Accounts ---------------------------------------------------------------
class SignUpView(CreateView):
    form_class = UserCreationForm
    template_name = "registration/signup.html"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect("dashboard")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        user = form.save()
        login(self.request, user)
        return redirect("dashboard")


# --- Dashboard --------------------------------------------------------------
class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = "tasks/dashboard.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        tasks = Task.objects.filter(owner=self.request.user)
        today = timezone.localdate()
        S = Task.Status

        counts = tasks.aggregate(
            total=Count("id"),
            todo=Count("id", filter=Q(status=S.TODO)),
            in_progress=Count("id", filter=Q(status=S.IN_PROGRESS)),
            done=Count("id", filter=Q(status=S.DONE)),
            overdue=Count("id", filter=Q(due_date__lt=today) & ~Q(status=S.DONE)),
        )
        total = counts["total"]

        def pct(n):
            return round(n * 100 / total) if total else 0

        counts["todo_pct"] = pct(counts["todo"])
        counts["in_progress_pct"] = pct(counts["in_progress"])
        counts["done_pct"] = pct(counts["done"])

        ctx["counts"] = counts
        ctx["attention"] = (
            tasks.exclude(status=S.DONE)
            .filter(due_date__isnull=False, due_date__lte=today + timedelta(days=7))
            .order_by("due_date")[:6]
        )
        ctx["recent"] = tasks.order_by("-updated_at")[:5]
        ctx["note_count"] = Note.objects.filter(owner=self.request.user).count()
        return ctx


# --- Tasks ------------------------------------------------------------------
class TaskListView(OwnedMixin, ListView):
    model = Task
    template_name = "tasks/task_list.html"
    context_object_name = "tasks"
    paginate_by = 12

    def get_queryset(self):
        qs = super().get_queryset()
        q = self.request.GET.get("q", "").strip()
        status = self.request.GET.get("status", "")
        priority = self.request.GET.get("priority", "")
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q))
        if status in Task.Status.values:
            qs = qs.filter(status=status)
        if priority in Task.Priority.values:
            qs = qs.filter(priority=priority)
        # Open tasks first, soonest due date first, tasks without a date last.
        done_last = Case(When(status=Task.Status.DONE, then=1), default=0, output_field=IntegerField())
        return qs.order_by(done_last, F("due_date").asc(nulls_last=True), "-created_at")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        params = self.request.GET.copy()
        params.pop("page", None)
        ctx["querystring"] = params.urlencode()
        ctx["q"] = self.request.GET.get("q", "").strip()
        ctx["current_status"] = self.request.GET.get("status", "")
        ctx["current_priority"] = self.request.GET.get("priority", "")
        ctx["statuses"] = Task.Status.choices
        ctx["priorities"] = Task.Priority.choices
        return ctx


class TaskCreateView(LoginRequiredMixin, SuccessMessageMixin, CreateView):
    model = Task
    form_class = TaskForm
    template_name = "tasks/task_form.html"
    success_url = reverse_lazy("task_list")
    success_message = "Task created."

    def get_initial(self):
        initial = super().get_initial()
        status = self.request.GET.get("status", "")
        if status in Task.Status.values:
            initial["status"] = status
        return initial

    def form_valid(self, form):
        form.instance.owner = self.request.user
        return super().form_valid(form)


class TaskUpdateView(OwnedMixin, SuccessMessageMixin, UpdateView):
    model = Task
    form_class = TaskForm
    template_name = "tasks/task_form.html"
    success_url = reverse_lazy("task_list")
    success_message = "Task saved."


class TaskDeleteView(OwnedMixin, SuccessMessageMixin, DeleteView):
    model = Task
    template_name = "tasks/task_confirm_delete.html"
    success_url = reverse_lazy("task_list")
    success_message = "Task deleted."


class TaskMoveView(LoginRequiredMixin, View):
    """POST-only: change a task's status (used by the board and the list)."""

    http_method_names = ["post"]

    def post(self, request, pk):
        task = get_object_or_404(Task, pk=pk, owner=request.user)
        status = request.POST.get("status", "")
        if status not in Task.Status.values:
            return HttpResponseBadRequest("Invalid status")
        task.status = status
        task.save(update_fields=["status", "updated_at"])
        target = request.POST.get("next", "")
        if target and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}):
            return redirect(target)
        return redirect("board")


class BoardView(LoginRequiredMixin, TemplateView):
    template_name = "tasks/board.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        tasks = list(
            Task.objects.filter(owner=self.request.user).order_by(
                F("due_date").asc(nulls_last=True), "-created_at"
            )
        )
        ctx["columns"] = [
            {"value": value, "label": label, "tasks": [t for t in tasks if t.status == value]}
            for value, label in Task.Status.choices
        ]
        return ctx


# --- Notes ------------------------------------------------------------------
class NoteListView(OwnedMixin, ListView):
    model = Note
    template_name = "tasks/note_list.html"
    context_object_name = "notes"

    def get_queryset(self):
        qs = super().get_queryset().select_related("task")
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(body__icontains=q))
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["q"] = self.request.GET.get("q", "").strip()
        return ctx


class NoteFormMixin:
    model = Note
    form_class = NoteForm
    template_name = "tasks/note_form.html"
    success_url = reverse_lazy("note_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs


class NoteCreateView(NoteFormMixin, LoginRequiredMixin, SuccessMessageMixin, CreateView):
    success_message = "Note created."

    def form_valid(self, form):
        form.instance.owner = self.request.user
        return super().form_valid(form)


class NoteUpdateView(NoteFormMixin, OwnedMixin, SuccessMessageMixin, UpdateView):
    success_message = "Note saved."


class NoteDeleteView(OwnedMixin, SuccessMessageMixin, DeleteView):
    model = Note
    template_name = "tasks/note_confirm_delete.html"
    success_url = reverse_lazy("note_list")
    success_message = "Note deleted."
