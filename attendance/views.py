from django.shortcuts import render
from django.utils import timezone
from django.http import JsonResponse
from datetime import time, timedelta
import json
#MDB파일 관련
from django.conf import settings
import subprocess
import os
from io import StringIO
import pandas as pd
#모델가져오기
from .models import Attendance
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
# Create your views here.

#MDB파일 출근데이터 기록하기
def mdbfile_record(request):
    if request.method == 'POST':
        if 'file' not in request.FILES:
            return JsonResponse({'success':False, 'message': '파일이 없습니다.'})

        #파일가져오기
        uploaded_file = request.FILES['file']

        #파일 저장 경로 설정
        save_path = os.path.join(settings.MEDIA_ROOT, uploaded_file.name)

        #파일저장
        with open(save_path, 'wb+') as destination:
            for chunk in uploaded_file.chunks():
                destination.write(chunk)

        print(f"파일이 {save_path}에 저장되었습니다.")

        try:
            # 카드번호와 사원번호가 매칭된 엑셀파일 가져오기
            excel_path = os.path.join(settings.MDEIA_ROOT, 'card_idnumber.xlsx')
            #엑셀파일에서 데이터 읽기
            excel_df = pd.read_excel(excel_path, engine='openpyxl')

            #MDB파일 CSV로 변환
            table_name = 'attendancetime'
            command = ['mdb-export', save_path, table_name]
            result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

            if result.returncode != 0:
                print(f"Error: {result.stderr}")
                return JsonResponse({'success': False, 'message': f'명령 실행 중 오류 발생: {result.stderr}'})

            #데이터 프레임 읽기
            data = StringIO(result.stdout)
            df = pd.read_csv(data)

            #필요한 필드 선택
            required_fields = ['e_date', 'e_time', 'e_id', 'e_name', 'e_mode']
            #필드 누락확인
            for field in required_fields:
                if field not in df.columns:
                    return JsonResponse({'success': False, 'message': f'필드{field}가 누락되었습니다.'})

            #데이터프레임에서 필요한 열 추출
            df_filterd = df[required_fields].copy()
            three_days_ago = datetime.now() - timedelta(days=3)
            three_days_ago_str = three_days_ago.date()

            #날짜와 시간을 변환해서 저장
            df_filterd.loc[:,'e_date'] = pd.to_datetime(df_filterd['e_date'],format="%Y%m%d",errors='coerce').dt.date
            #삽입하는 데이터를 현재날짜에서 3일전까지의 데이터만 넣는걸로 설정 예) 현날짜가 11일이면 8일부터 삽입
            df_filterd = df_filterd[df_filterd['e_date'] >= three_days_ago_str]
            #시간을 분까지만 표시
            df_filterd.loc[:,'e_time'] = pd.to_datetime(df_filterd['e_time'], format="%H%M%S",errors='coerce').dt.rount('min').dt.time

            #결측값 제거
            df_filterd.dropna(subset=['e_date','e_time'], inplace=True)

            #날짜,시간을 기준으로 정렬
            df_filterd = df_filterd.sort_values(by=['e_date','e_time'],ascending=[True, True])

            for i, row in df_filterd.iterrows():
                #e_name이 Nan이면 넘어가기
                if pd.isna(row['e_name']):
                    continue
                check_date = row['e_date']
                employee_number = row['e_id']
                name = row['e_name']
                check_time = row['e_time']
                check_mode = row['e_mode']
                #엑셀에서 카드번호와 매칭되는 사원번호 가져오기
                matching_rows = excel_df[excel_df['카드ID'] == employee_number]
                if not matching_rows.empty:
                    employee_number = matching_rows['사원번호'].values[0]

                #등록시간 변환
                check_combine_time = datetime.combine(check_date, check_time)

                if check_mode == 1 or check_mode == 2:
                    if check_mode == 1:
                        #출근생성
                        attendance_record = Attendance.objects.filter(
                            name = name,
                            employee_number = employee_number,
                            check_date = check_date,
                            check_in_time = check_time,
                        )
                        if not attendance_record.exists():
                            #check_date의 데이터가 없기에 새로 생성
                            #데이터조회떄 created_time을 참고하기떄문에 created_time에 카드가 찍힌날짜와 시간 대입
                            Attendance.objects.create(
                                name = name,
                                employee_number = employee_number,
                                check_date = check_date,
                                check_in_time = check_time,
                                check_in_place_name = "본사",
                                check_in_location = "본사",
                                check_in_type = "카드",
                                created_time = check_combine_time
                            )
                        else:
                            #이미 생성된 데이터이기에 넘어갑니다.
                            continue
                    elif check_mode == 2:
                        attendance_record = Attendance.objects.filter(
                            name = name,
                            employee_number = employee_number,
                            check_date = check_date,
                        )
                        if attendance_record.exists():
                            #해당날짜의 출근데이터가 있음
                            #여러개인지 확인
                            if len(attendance_record) >= 2:
                                match_attendance = attendance_record.filter(check_out_time = check_time).first()
                                if match_attendance:
                                    continue
                                else:
                                    #출근기록이 2개이상이므로 정렬한후 최근값을 가져온다
                                    recent_attendance = None
                                    for i in match_attendance.order_by('-check_in_time'):
                                        if i.check_in_time < check_time:
                                            recent_attendance = i
                                            break
                                    if recent_attendance.business_start_time == time(0,0,0):
                                        #출장출발기록이 없으면 정상퇴근처리
                                        recent_attendance.check_out_time = check_time
                                        recent_attendance.check_out_place_name = "본사"
                                        recent_attendance.check_out_location = "본사"
                                        recent_attendance.check_type = "카드"
                                        recent_attendance.save()
                                    else:
                                        #출장을하고 카드로 퇴근을 했기에 출장복귀에 퇴근기록을 넣음
                                        recent_attendance.check_out_time = check_time
                                        recent_attendance.business_end_time = check_time
                                        recent_attendance.check_out_place_name = "본사"
                                        recent_attendance.check_out_location = "본사"
                                        recent_attendance.check_type = "카드"
                                        recent_attendance.save()
                            else:
                                #해당날짜에 출퇴근기록이 1개라면 바로값을 넣는다.
                                recent_attendance = recent_attendance[0]
                                if recent_attendance.business_start_time == time(0, 0, 0):
                                    #출장출발이 없는 정상퇴근
                                    recent_attendance.check_out_time = check_time
                                    recent_attendance.check_out_place_name = "본사"
                                    recent_attendance.check_out_location = "본사"
                                    recent_attendance.check_type = "카드"
                                    recent_attendance.save()
                                else:
                                    #출장출발이 있어 복귀시간에 퇴근시간을 넣음
                                    recent_attendance.check_out_time = check_time
                                    recent_attendance.business_end_time = check_time
                                    recent_attendance.check_out_place_name = "본사"
                                    recent_attendance.check_out_location = "본사"
                                    recent_attendance.check_out_type = "카드"
                                    recent_attendance.save()
                else:
                    #출근은 1 퇴근은 2 그외에는 쓸모없으니 패스한다
                    continue

            return JsonResponse({'success': True, 'message': 'MDB파일로 출퇴근 처리 완료'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': f'MDB 파일 처리하는중 오류발생'})
    else:
        return JsonResponse({'success': False, 'message': "잘못된 요청입니다."})







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
                    check_in_location = check_in_location,
                    check_in_type = "웹"
                )
                return JsonResponse({'success': True, 'message': f'{check_in_time}에 출근처리 되었습니다.'})
            else:
                print("최근기록에 츨징츨발기록이 있고 출퇴근기록이 없으므로 출장출발기록에 출근을 넣는다.")
                business_check.check_in_time = check_in_time
                business_check.check_in_place_name = check_in_place_name
                business_check.check_in_location = check_in_location
                business_check.check_in_type = "웹"
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
                check_in_location = check_in_location,
                check_in_type = "웹"
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
                check_out_location = check_out_location,
                check_out_type = "웹"
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
                    recent_attendance.check_out_type = "웹"
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
                        check_out_location=check_out_location,
                        check_out_type="웹"
                    )
                    return JsonResponse({'success': True, 'message': f'{check_out_time}에 퇴근처리 되었습니다.'})
            else:
                # 최근기록날짜와 퇴근기록날짜가 같은거는 당일퇴근이기에 최근기록에 퇴근기록을 씌우면 된다.
                recent_attendance.check_out_time = check_out_time
                recent_attendance.check_out_place_name = check_out_place_name
                recent_attendance.check_out_location = check_out_location
                recent_attendance.check_out_type = "웹"
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
                check_out_location=check_out_location,
                check_out_type = "웹"
            )
            return JsonResponse({'success': True, 'message': f'{check_out_time}에 퇴근처리가 되었습니다.'})
