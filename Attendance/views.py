from django.shortcuts import render
from django.utils import timezone
from django.http import JsonResponse
from datetime import time, timedelta
import json
#모델가져오기
from .models import Attendance
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
# Create your views here.

def business_start(request):
    if request.method == "POST":
        data = json.loads(request.body)
        name = data.get('name','')
        employee_number = data.get('employee_number','')
        check_date = data.get('check_date','')
        business_start_time = data.get('buiness_start_time','')
        business_start_place= data.get('place_name','')
        #날짜,시간 변형
        check_date = datetime.strptime(check_date,"%Y-%m-%d").date()
        business_start_time = datetime.strptime(business_start_time, "%H:%M").time()
        Attendance.objects.create(
            name = name,
            employee_number = employee_number,
            check_date = check_date,
            business_start_time = business_start_time,
            business_start_place = business_start_place,
        )
        return JsonResponse({'success': True, 'message': f'{business_start_time}에 출장출발 처리 되었습니다.'})
    else:
        return JsonResponse({'success': False, 'message': "잘못된 요청입니다."})
def business_end(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        name = data.get('name','')
        employee_number = data.get('employee_number', '')
        check_date = data.get('check_date', '')
        business_end_time = data.get('business_end_time','')
        business_end_place = data.get('place_name','')
        #날짜,시간 형태변경
        check_date = datetime.strptime(check_date,"%Y-%m-%d").date()
        business_end_time = datetime.strptime(business_end_time, "%H:%M").time()
        #가장최근기록에 복귀 데이터 넣기
        recent_attendance = Attendance.objects.filter(name=name,employee_number=employee_number).order_by('-check_date','-created_time').first()
        #예)17일출장출발 18일 새벽복귀
        if recent_attendance.check_date != check_date:
            if recent_attendance.check_out_time == time(0,0,0):
                #최근기록에 퇴근이 없을시 퇴근을 먼저하라는 메시지를 반환한다.
                return JsonResponse({'success': False, 'message': '퇴근처리가 되있지않습니다.\n퇴근부터 해주시길 바랍니다.'})
            else:
                #퇴근이 되어있을경우 그 기록에 복귀기록을 씌운다.
                #날짜가 다른복귀이기에 퇴근처럼 24초를 더해서 처리한다.
                business_end_time = datetime.combine(check_date,business_end_time) + timedelta(seconds=24)
                business_end_time = business_end_time.time()
                recent_attendance.business_end_time = business_end_time
                recent_attendance.business_end_place = business_end_place
                recent_attendance.save()
                return JsonResponse({'success': True, 'message': f'{business_end_time}에 출장복귀처리가 되었습니다.'})
        else:
            #날짜가 같으면 당일 출장복귀이기에 최근기록에 복귀기록을 씌운다.
            if recent_attendance.check_out_time == time(0,0,0):
                return JsonResponse({'success': False, 'message': '퇴근처리가 되있지않습니다.\n퇴근부터 해주시길 바랍니다.'})
            if recent_attendance.business_end_time != time(0,0,0):
                #최근기록의 복귀시간이 00:00이 아니면 복귀를 했기에 복귀처리된시간을 반환해준다.
                return JsonResponse({'success': False, 'message': f'{recent_attendance.check_date}일 {recent_attendance.business_end_time}자로 복귀처리가되었습니다.'})
            #두조건을 통과하면 당일복귀처리를 한다.
            recent_attendance.business_end_time = business_end_time
            recent_attendance.business_end_place = business_end_place
            recent_attendance.save()
            return JsonResponse({'success': True, 'message': f'{business_end_time}에 출장복귀 처리 되었습니다.'})
    else:
        return JsonResponse({'success': False, 'message': "잘못된 요청입니다."})


def check_in(request):
    if request.method == "POST":
        data = json.loads(request.body)
        name = data.get('name','')
        employee_number = data.get('employee_number','')
        check_in_place_name = data.get('place_name','')
        check_in_location = data.get('location','')
        check_date = data.get('check_date','')
        check_in_time = data.get('check_time','')
        #날짜,시간 형태변경
        check_date = datetime.strptime(check_date,"%Y-%m-%d").date()
        check_in_time = datetime.strptime(check_in_time, "%H:%M").time()
        #출장출발유무 체크
        business_check = Attendance.objects.filter(name=name,employee_number=employee_number).order_by(-'created_time').first()
        if business_check.business_start != time(0,0,0):
            print("출장기록이 있으므로 출퇴근 기록을 확인합니다.")
            if business_check_in_time != time(0,0,0) or business_check.check_out_time != time(0,0,0):
                print("최근기록에 출장출발이 있고 출근이나 퇴근이 기록되어있으므로 새로운출퇴근기록을 만듭니다.")
                Attendance.objects.create(
                    name = name,
                    employee_number = employee_number,
                    check_date = check_date,
                    check_in_time = check_in_time,
                    check_in_place_name = check_in_place_name,
                    check_in_location = check_in_location
                )
                return JsonResponse({'success': True, 'message': f'{check_in_time}에 출근처리 되었습니다.'})
            else:
                print("최근기록에 츨징츨발기록이 있고 출퇴근기록이 없으므로 출장출발기록에 출근을 넣는다.")
                business_check.check_in_time = check_in_time
                business_check.check_in_place_name = check_in_place_name
                business_check.check_in_location = check_in_location
                business_check.save()
                return JsonResponse({'success': True, 'message': f'{check_in_time}에 출근처리 되었습니다.'})
        #출근데이터생성
        else:
            print("출장출발기록이 없다면 새 데이터를 만듭니다.")
            Attendance.objects.create(
                name = name,
                employee_number = employee_number,
                check_date = check_date,
                check_in_time = check_in_time,
                check_in_place_name = check_in_place_name,
                check_in_location = check_in_location
            )
            #출근메시지 반환
            return JsonResponse({'success': True, 'message': f'{check_in_time}에 출근처리 되었습니다.'})


def check_out(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        name = data.get('name','')
        employee_number = data.get('employee_number','')
        check_out_place_name = data.get('place_name','')
        check_out_location = data.get('location','')
        check_date = data.get('check_date','')
        check_out_time = data.get('check_time','')
        #날짜,시간 형태변경
        check_date = datetime.strptime(check_date,"%Y-%m-%d").date()
        check_out_time = datetime.strptime(check_out_time, "%H:%M").time()
        #최근 출근데이터 찾기
        recent_attendance = Attendance.objects.filter(name=name, employee_number=employee_number).order_by("-check_date",'-created_time').first()

        #출퇴근데이터가 없는경우
        if not recent_attendance:
            Attendance.objects.create(
                name = name,
                employee_number = employee_number,
                check_date = check_date,
                check_out_time = check_out_time,
                check_out_place_name = check_out_place_name,
                check_out_location = check_out_location
            )
            return JsonResponse({'success': True, 'message': f'{check_out_time}에 퇴근처리가 되었습니다.'})

        if recent_attendance and recent_attendance.business_end_time == time(0,0,0):
            #최근기록과 퇴근날짜가 다른지 확인
            if recent_attendance.check_date != check_date:
                #날짜가 다르다면 새벽에 퇴근을 의미하는것이고 퇴근시간이 00인지 확인
                if recent_attendance.check_out_time == time(0, 0, 0):
                    # 24시가넘어가는 퇴근을 구분을 위해 초단위에 24초를 더해서 저장한다.
                    check_out_time = datetime.combine(check_date, check_out_time) + timedelta(seconds=24)
                    check_out_time = check_out_time.time()
                    recent_attendance.check_out_time = check_out_time
                    recent_attendance.check_out_place_name = check_out_place_name
                    recent_attendance.check_out_location = check_out_location
                    recent_attendance.save()
                    check_out_time = check_out_time.strftime("%H:%M")
                    return JsonResponse({'success': True, 'message': f'{check_out_time}에 퇴근처리 되었습니다.'})
                else:
                    # 퇴근기록날짜와 최근기록날짜가 다르고 최근기록에 퇴근기록이 있을경우 출근을누락했거나 잘못누른경우을 뜻함
                    Attendance.objects.create(
                        name=name,
                        employee_number=employee_number,
                        check_date=check_date,
                        check_out_time=check_out_time,
                        check_out_place_name=check_out_place_name,
                        check_out_location=check_out_location
                    )
                    return JsonResponse({'success': True, 'message': f'{check_out_time}에 퇴근처리 되었습니다.'})
            else:
                # 최근기록날짜와 퇴근기록날짜가 같은거는 당일퇴근이기에 최근기록에 퇴근기록을 씌우면 된다.
                recent_attendance.check_out_time = check_out_time
                recent_attendance.check_out_place_name = check_out_place_name
                recent_attendance.check_out_location = check_out_location
                recent_attendance.save()
                return JsonResponse({'success': True, 'message': f'{check_out_time}에 퇴근처리가 되었습니다.'})
        else:
            #출장복귀를완료한상태이기때문에 새로운 출퇴근데이터를 생성한다.
            Attendance.objects.create(
                name=name,
                employee_number=employee_number,
                check_date=check_date,
                check_out_time=check_out_time,
                check_out_place_name=check_out_place_name,
                check_out_location=check_out_location
            )
            return JsonResponse({'success': True, 'message': f'{check_out_time}에 퇴근처리가 되었습니다.'})
