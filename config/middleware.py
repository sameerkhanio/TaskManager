from django.http import HttpResponse


class HealthCheckMiddleware:
    """
    Answers /health/ before Django checks the Host header.

    An ALB health check calls each EC2 instance by its private IP, which is not in
    ALLOWED_HOSTS, so it would normally get a 400 and the instance would be marked
    unhealthy. Answering here avoids that without opening ALLOWED_HOSTS to everything.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path == "/health/":
            return HttpResponse("ok", content_type="text/plain")
        return self.get_response(request)
