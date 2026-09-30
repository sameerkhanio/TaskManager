from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Note, Task

User = get_user_model()


class BaseCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("sameer", password="pass-12345-x")
        self.other = User.objects.create_user("other", password="pass-12345-x")
        self.client.login(username="sameer", password="pass-12345-x")

    def make_task(self, owner=None, **kw):
        kw.setdefault("title", "Task")
        return Task.objects.create(owner=owner or self.user, **kw)


class AuthTests(TestCase):
    def test_pages_require_login(self):
        for name in ["dashboard", "task_list", "task_create", "board", "note_list", "note_create"]:
            resp = self.client.get(reverse(name))
            self.assertEqual(resp.status_code, 302, name)
            self.assertIn("/accounts/login/", resp["Location"])

    def test_signup_logs_user_in(self):
        resp = self.client.post(
            reverse("signup"),
            {"username": "newuser", "password1": "a-Strong-pass-77", "password2": "a-Strong-pass-77"},
        )
        self.assertRedirects(resp, reverse("dashboard"))
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 200)

    def test_health_check_needs_no_login_or_valid_host(self):
        resp = self.client.get("/health/", HTTP_HOST="10.0.3.17")
        self.assertEqual(resp.status_code, 200)


class TaskTests(BaseCase):
    def test_create_sets_owner(self):
        resp = self.client.post(reverse("task_create"), {
            "title": "Write report", "description": "", "status": "todo", "priority": "high", "due_date": "",
        })
        self.assertRedirects(resp, reverse("task_list"))
        task = Task.objects.get()
        self.assertEqual(task.owner, self.user)

    def test_create_prefills_status_from_query(self):
        resp = self.client.get(reverse("task_create") + "?status=in_progress")
        self.assertEqual(resp.context["form"].initial["status"], "in_progress")

    def test_overdue_logic(self):
        yesterday = timezone.localdate() - timedelta(days=1)
        self.assertTrue(self.make_task(due_date=yesterday).is_overdue)
        self.assertFalse(self.make_task(due_date=yesterday, status="done").is_overdue)
        self.assertFalse(self.make_task().is_overdue)

    def test_users_cannot_touch_each_others_tasks(self):
        theirs = self.make_task(owner=self.other, title="Secret")
        self.assertEqual(self.client.get(reverse("task_update", args=[theirs.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("task_delete", args=[theirs.pk])).status_code, 404)
        resp = self.client.post(reverse("task_move", args=[theirs.pk]), {"status": "done"})
        self.assertEqual(resp.status_code, 404)
        self.assertNotContains(self.client.get(reverse("task_list")), "Secret")
        theirs.refresh_from_db()
        self.assertEqual(theirs.status, "todo")

    def test_list_filters_and_search(self):
        self.make_task(title="Alpha", status="done")
        self.make_task(title="Beta", priority="high")
        resp = self.client.get(reverse("task_list"), {"status": "done"})
        self.assertEqual([t.title for t in resp.context["tasks"]], ["Alpha"])
        resp = self.client.get(reverse("task_list"), {"q": "bet"})
        self.assertEqual([t.title for t in resp.context["tasks"]], ["Beta"])
        resp = self.client.get(reverse("task_list"), {"status": "bogus"})
        self.assertEqual(len(resp.context["tasks"]), 2)

    def test_delete(self):
        task = self.make_task()
        self.assertRedirects(self.client.post(reverse("task_delete", args=[task.pk])), reverse("task_list"))
        self.assertFalse(Task.objects.exists())


class BoardTests(BaseCase):
    def test_move_changes_status_and_redirects(self):
        task = self.make_task()
        resp = self.client.post(reverse("task_move", args=[task.pk]), {"status": "in_progress", "next": "/board/"})
        self.assertRedirects(resp, "/board/")
        task.refresh_from_db()
        self.assertEqual(task.status, "in_progress")

    def test_move_rejects_bad_status_and_get(self):
        task = self.make_task()
        self.assertEqual(self.client.post(reverse("task_move", args=[task.pk]), {"status": "nope"}).status_code, 400)
        self.assertEqual(self.client.get(reverse("task_move", args=[task.pk])).status_code, 405)

    def test_move_ignores_external_next_url(self):
        task = self.make_task()
        resp = self.client.post(reverse("task_move", args=[task.pk]), {"status": "done", "next": "https://evil.example/"})
        self.assertRedirects(resp, reverse("board"))

    def test_board_groups_by_status(self):
        self.make_task(title="A", status="todo")
        self.make_task(title="B", status="done")
        cols = {c["value"]: [t.title for t in c["tasks"]] for c in self.client.get(reverse("board")).context["columns"]}
        self.assertEqual(cols, {"todo": ["A"], "in_progress": [], "done": ["B"]})


class DashboardTests(BaseCase):
    def test_counts(self):
        yesterday = timezone.localdate() - timedelta(days=1)
        self.make_task(status="todo", due_date=yesterday)
        self.make_task(status="in_progress")
        self.make_task(status="done", due_date=yesterday)
        self.make_task(owner=self.other, status="done")
        counts = self.client.get(reverse("dashboard")).context["counts"]
        self.assertEqual(
            (counts["total"], counts["todo"], counts["in_progress"], counts["done"], counts["overdue"]),
            (3, 1, 1, 1, 1),
        )

    def test_empty_dashboard_renders(self):
        self.assertContains(self.client.get(reverse("dashboard")), "Create your first task")


class NoteTests(BaseCase):
    def test_create_and_link_to_own_task_only(self):
        mine = self.make_task(title="Mine")
        theirs = self.make_task(owner=self.other, title="Theirs")
        ok = self.client.post(reverse("note_create"), {"title": "N1", "body": "b", "task": mine.pk})
        self.assertRedirects(ok, reverse("note_list"))
        bad = self.client.post(reverse("note_create"), {"title": "N2", "body": "b", "task": theirs.pk})
        self.assertEqual(bad.status_code, 200)  # form re-rendered with an error
        self.assertEqual(Note.objects.count(), 1)

    def test_notes_are_private(self):
        note = Note.objects.create(owner=self.other, title="Private")
        self.assertEqual(self.client.get(reverse("note_update", args=[note.pk])).status_code, 404)
        self.assertNotContains(self.client.get(reverse("note_list")), "Private")
