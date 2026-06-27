from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from ..decorators import school_only
from ..models import Notification
from ..forms import NotificationForm


@school_only
def notification_list(request):
    school = request.user.school
    notifications = Notification.objects.filter(school=school)
    return render(request, 'school/notifications/list.html', {
        'notifications': notifications
    })


@school_only
def notification_create(request):
    school = request.user.school
    if request.method == 'POST':
        form = NotificationForm(request.POST, request.FILES)
        if form.is_valid():
            notification = form.save(commit=False)
            notification.school = school
            notification.save()
            messages.success(request, 'Notification created successfully.')
            return redirect('notification_list')
    else:
        form = NotificationForm()
    
    return render(request, 'school/notifications/form.html', {
        'form': form,
        'title': 'Create Notification'
    })


@school_only
def notification_edit(request, pk):
    school = request.user.school
    notification = get_object_or_404(Notification, pk=pk, school=school)
    if request.method == 'POST':
        form = NotificationForm(request.POST, request.FILES, instance=notification)
        if form.is_valid():
            form.save()
            messages.success(request, 'Notification updated successfully.')
            return redirect('notification_list')
    else:
        form = NotificationForm(instance=notification)
        
    return render(request, 'school/notifications/form.html', {
        'form': form,
        'notification': notification,
        'title': 'Edit Notification'
    })


@school_only
def notification_delete(request, pk):
    school = request.user.school
    notification = get_object_or_404(Notification, pk=pk, school=school)
    if request.method == 'POST':
        notification.delete()
        messages.success(request, 'Notification deleted successfully.')
        return redirect('notification_list')
    return render(request, 'confirm_delete.html', {
        'name': notification.title
    })


@school_only
@require_POST
def notification_toggle_publish(request, pk):
    school = request.user.school
    notification = get_object_or_404(Notification, pk=pk, school=school)
    notification.is_published = not notification.is_published
    notification.save()
    return JsonResponse({
        'ok': True,
        'is_published': notification.is_published
    })
