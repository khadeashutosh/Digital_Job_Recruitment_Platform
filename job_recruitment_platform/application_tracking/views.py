from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from job_management.models import User
from application_tracking.enums import ApplicationStatus
from common.tasks import send_email

from .forms import JobAdvertForm, JobApplicationForm
from .models import JobAdvert, JobApplication


@login_required
def create_advert(request: HttpRequest):
    form = JobAdvertForm(request.POST or None)
    if form.is_valid():
        instance = form.save(commit=False)
        instance.created_by = request.user
        instance.save()
        messages.success(request, "Advert created. You can now receive applications.")
        return redirect("job_advert", advert_id=instance.id)

    return render(request, "create_advert.html", {
        "job_advert_form": form,
        "title": "Create a new advert",
        "btn_text": "Create advert"
    })


def list_adverts(request: HttpRequest):
    active_jobs = JobAdvert.objects.active()
    paginator = Paginator(active_jobs, 10)
    page = request.GET.get("page")
    paginated_adverts = paginator.get_page(page)
    return render(request, "home.html", {"job_adverts": paginated_adverts})


def get_advert(request: HttpRequest, advert_id):
    job_advert = get_object_or_404(JobAdvert, pk=advert_id)
    form = JobApplicationForm()
    return render(request, "advert.html", {
        "job_advert": job_advert,
        "application_form": form
    })


@login_required
def update_advert(request: HttpRequest, advert_id):
    advert = get_object_or_404(JobAdvert, pk=advert_id)
    if request.user != advert.created_by:
        return HttpResponseForbidden("You can only update an advert created by you.")

    form = JobAdvertForm(request.POST or None, instance=advert)
    if form.is_valid():
        form.save()
        messages.success(request, "Advert updated successfully.")
        return redirect("job_advert", advert_id=advert.id)

    return render(request, "create_advert.html", {
        "job_advert_form": form,
        "btn_text": "Update advert"
    })


@login_required
def delete_advert(request: HttpRequest, advert_id):
    advert = get_object_or_404(JobAdvert, pk=advert_id)
    if request.user != advert.created_by:
        return HttpResponseForbidden("You can only delete an advert created by you.")

    advert.delete()
    messages.success(request, "Advert deleted successfully.")
    return redirect("my_jobs")


def apply(request: HttpRequest, advert_id):
    advert = get_object_or_404(JobAdvert, pk=advert_id)
    if request.method == "POST":
        form = JobApplicationForm(request.POST, request.FILES)
        if form.is_valid():
            email = form.cleaned_data["email"]
            if advert.applications.filter(email__iexact=email).exists():
                messages.error(request, "You have already applied for this position.")
                return redirect("job_advert", advert_id=advert.id)

            application = form.save(commit=False)
            application.job_advert = advert
            application.save()
            messages.success(request, "Application submitted successfully.")
            return redirect("job_advert", advert_id=advert.id)
    else:
        form = JobApplicationForm()

    return render(request, "advert.html", {
        "job_advert": advert,
        "application_form": form
    })


@login_required
def my_applications(request: HttpRequest):
    applications = JobApplication.objects.filter(email=request.user.email)
    paginator = Paginator(applications, 10)
    page = request.GET.get("page")
    paginated = paginator.get_page(page)
    return render(request, "my_applications.html", {"my_applications": paginated})


@login_required
def my_jobs(request: HttpRequest):
    jobs = JobAdvert.objects.filter(created_by=request.user)
    paginator = Paginator(jobs, 10)
    page = request.GET.get("page")
    paginated = paginator.get_page(page)
    return render(request, "my_jobs.html", {
        "my_jobs": paginated,
        "current_date": timezone.now().date()
    })


@login_required
def advert_applications(request: HttpRequest, advert_id):
    advert = get_object_or_404(JobAdvert, pk=advert_id)
    if request.user != advert.created_by:
        return HttpResponseForbidden("You can only view applications for your own advert.")

    applications = advert.applications.all()
    paginator = Paginator(applications, 10)
    page = request.GET.get("page")
    paginated = paginator.get_page(page)

    return render(request, "advert_applications.html", {
        "applications": paginated,
        "advert": advert
    })


@login_required
def decide(request: HttpRequest, job_application_id):
    job_application = get_object_or_404(JobApplication, pk=job_application_id)
    if request.user != job_application.job_advert.created_by:
        return HttpResponseForbidden("You can only decide on applications for your own advert.")

    if request.method == "POST":
        status = request.POST.get("status")
        job_application.status = status
        job_application.save(update_fields=["status"])
        messages.success(request, f"Application status updated to {status}.")

        if status == ApplicationStatus.REJECTED:
            context = {
                "applicant_name": job_application.name,
                "job_title": job_application.job_advert.title,
                "company_name": job_application.job_advert.company_name,
            }
            send_email(
                f"Application Outcome for {job_application.job_advert.title}",
                [job_application.email],
                "emails/job_application_update.html",
                context
            )

        return redirect("advert_applications", advert_id=job_application.job_advert.id)


def search(request: HttpRequest):
    keyword = request.GET.get("keyword")
    location = request.GET.get("location")
    result = JobAdvert.objects.search(keyword, location)
    paginator = Paginator(result, 10)
    page = request.GET.get("page")
    paginated = paginator.get_page(page)
    return render(request, "home.html", {"job_adverts": paginated})
