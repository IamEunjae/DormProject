from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import Lounge, Reservation
from datetime import timedelta
from django.contrib.auth import get_user_model

User = get_user_model()

@login_required
def lounge_list(request):
    now = timezone.localtime()
    allowed = (17 <= now.hour < 23)
    infos = []
    for lounge in Lounge.objects.all():
        active_res = Reservation.objects.filter(
            lounge=lounge,
            end_time__gt=now
        ).order_by('end_time').first()
        if active_res:
            remaining = active_res.end_time - now
            total_seconds = int(remaining.total_seconds())
            minutes, seconds = divmod(total_seconds, 60)
            remaining_str = f"{minutes}분 {seconds}초"
            # Determine state for current user
            if request.user == active_res.user or request.user in active_res.participants.all():
                state = 'using'      # 본인 사용중
            else:
                state = 'busy'       # 다른 사람 사용중
            infos.append({
                'number': lounge.number,
                'state': state,
                'remaining': remaining_str,
                'participants': active_res.participants.all(),
            })
        else:
            state = 'free'
            infos.append({
                'number': lounge.number,
                'state': state,
                'remaining': None,
                'participants': None,
            })
    return render(request, 'reservation/lounge_list.html', {
        'infos': infos,
        'allowed': allowed,
    })

@login_required
def reserve_lounge(request, number):
    now = timezone.localtime()
    if now.hour < 17 or now.hour >= 23:
        return redirect('reservation:lounge_list')
    lounge = get_object_or_404(Lounge, number=number)
    if request.method == 'POST':
        raw = request.POST.get('partners', '')
        partners = [s.strip() for s in raw.split(',') if s.strip()]
        res = Reservation.objects.create(
            user=request.user,
            lounge=lounge,
            start_time=now,
            end_time=now + timedelta(minutes=30)
        )
        # Ensure creator is participant
        res.participants.add(request.user)
        for sn in partners:
            try:
                u = User.objects.get(student_number=sn)
                res.participants.add(u)
            except User.DoesNotExist:
                messages.warning(request, f"학번 {sn}인 사용자를 찾을 수 없습니다.")
        return redirect('reservation:lounge_list')
    return redirect('reservation:lounge_list')