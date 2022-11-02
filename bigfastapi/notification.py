from fastapi import APIRouter
from datetime import datetime
from bigfastapi.db.database import get_db
from fastapi import Depends, status, HTTPException
from .models import notification_models as model
from .schemas import notification_schemas as schema, users_schemas as user_schema
from typing import List
from bigfastapi.services.auth_service import is_authenticated
from bigfastapi.utils import paginator
import sqlalchemy.orm as orm
from uuid import uuid4
from bigfastapi.models.organization_models import Organization
from fastapi.responses import JSONResponse
from .models.user_models import User
from .services.notification_services import (
    create_notification,
    create_notification_setting,
    fetch_existing_setting,
    update_notification_setting,
    get_notifications,
    check_group_member_exists
)
from bigfastapi.core.helpers import Helpers

app = APIRouter(tags=["Notification"])


@app.get("/notification/{notification_id}", response_model=schema.Notification)
def get_a_notification(notification_id: str, db: orm.Session = Depends(get_db)):
    """intro-->This endpoint allows you to details of a particular notification. You need to make a get request to the /notification/{notification_id} 

    paramDesc--> On get request the url takes a query parameter "notification_id"
        param-->notification_id: This is the unique identifier of the notification

    returnDesc-->On sucessful request, it returns
        returnBody--> details of the notification.
    """

    return model.notification_selector(id=notification_id, db=db)


@app.get("/notifications", response_model=schema.FetchNotificationsResponse)
async def get_user_notifications(
        organization_id: str,
        page: int = 1,
        size: int = 50,
        user: user_schema.User = Depends(is_authenticated),
        db: orm.Session = Depends(get_db)):

    """intro-->This endpoint allows you to retrieve all notifications from the database. To retrieve you need to make a get request to the /notifications endpoint


    returnDesc-->On sucessful request, it returns
        returnBody--> an array of notifications.
    """
    # validate user and organization
    await Helpers.check_user_org_validity(
        user_id=user.id, organization_id=organization_id, db=db

    )

    user_id = user.id

    # set pagination parameter
    page_size = 50 if size < 1 or size > 100 else size
    page_number = 1 if page <= 0 else page
    offset = await paginator.off_set(page=page_number, size=page_size)

    notifications, total_items = await get_notifications(user_id, organization_id,
                                                         db, page_size, offset)

    pointers = await paginator.page_urls(page=page_number, size=page_size,
                                         count=total_items, endpoint=f"/notifications")

    response = {"page": page, "size": page_size, "total": total_items,
                "previous_page": pointers['previous'], "next_page": pointers["next"], "items": notifications}

    for notification in notifications:
        print(notification)

    return response


@app.post("/notification", response_model=schema.Notification)
async def create_user_notification(
        notification: schema.NotificationCreate,
        user: user_schema.User = Depends(is_authenticated),
        db: orm.Session = Depends(get_db)):

    """intro-->This endpoint allows you to create a new notification. To create, you need to make a post request to the /notification endpoint with a required body of request as specified below

        reqBody-->message: This is the content of the notification
        reqBody-->recipient: This the receiver of the notification
        reqBody-->creator: This is the creator of the notification

    returnDesc-->On sucessful request, it returns
        returnBody--> the details of the newly created notification.
    """
    # organization and user check
    await Helpers.check_user_org_validity(
        user_id=user.id, organization_id=notification.organization_id, db=db
    )

    new_notification = create_notification(notification=notification, user=user, db=db)

    return new_notification


@app.get("/notifications-settings/{organization_id}", response_model=schema.NotificationSettingResponse)
async def get_org_notification_settings(
        organization_id: str,
        user: user_schema.User = Depends(is_authenticated),
        db: orm.Session = Depends(get_db)):

    """intro-->This endpoint allows you to retrieve all notifications from the database. To retrieve you need to make a get request to the /notifications endpoint


    returnDesc-->On sucessful request, it returns
        returnBody--> an array of notifications.
    """
    # validate user and organization
    await Helpers.check_user_org_validity(
        user_id=user.id, organization_id=organization_id, db=db
    )

    notification_settings = db.query(model.NotificationSetting).filter(
        model.NotificationSetting.organization_id == organization_id
    ).first()

    return notification_settings


@app.post("/notification-settings", response_model=schema.NotificationSettingResponse)
async def create_org_notification_settings(
        notification_setting: schema.NotificationSetting,
        user: user_schema.User = Depends(is_authenticated),
        db: orm.Session = Depends(get_db)):

    """intro-->This endpoint allows you to create a new notification. To create, you need to make a post request to the /notification endpoint with a required body of request as specified below

        reqBody-->message: This is the content of the notification
        reqBody-->recipient: This the receiver of the notification
        reqBody-->creator: This is the creator of the notification

    returnDesc-->On sucessful request, it returns
        returnBody--> the details of the newly created notification.
    """
    if user.is_superuser:

        # organization and user check
        await Helpers.check_user_org_validity(
            user_id=user.id, organization_id=notification_setting.organization_id, db=db
        )
        existing_org_setting = db.query(model.NotificationSetting).filter(
            model.NotificationSetting.organization_id == notification_setting.organization_id
        ).first()

        if existing_org_setting is None:
            new_notification_setting = create_notification_setting(
                notification_setting=notification_setting,
                user=user,
                db=db
            )
            return new_notification_setting

        return JSONResponse(
            {"message": "Organization already has notification settings, another cannot be created"},
            status_code=status.HTTP_409_CONFLICT
        )

    return JSONResponse(
        {"message": "Only an Admin can perform this action"},
        status_code=status.HTTP_401_UNAUTHORIZED
    )


@app.put("/notification-settings/{setting_id}", response_model=schema.NotificationSettingResponse)
async def update_org_notification_settings(
        setting_id: str,
        notification_setting: schema.NotificationSettingUpdate,
        user: user_schema.User = Depends(is_authenticated),
        db: orm.Session = Depends(get_db)):

    if user.is_superuser:

        # organization and user check
        await Helpers.check_user_org_validity(
            user_id=user.id, organization_id=notification_setting.organization_id, db=db
        )

        existing_setting = await fetch_existing_setting(
            id=setting_id,
            organization_id=notification_setting.organization_id,
            db=db
        )
        updated_notification_setting = await update_notification_setting(
            notification_setting=notification_setting,
            fetched_setting=existing_setting,
            user=user,
            db=db
        )

        return updated_notification_setting

    return JSONResponse(
        {"message": "Only an Admin can perform this action"},
        status_code=status.HTTP_401_UNAUTHORIZED
    )



@app.get("/notification-groups", response_model=List[schema.NotificationGroupResponse])
async def get_all_notification_groups(
    organization_id: str,
    user: user_schema.User = Depends(is_authenticated),
    db: orm.Session = Depends(get_db)
):
    #organization and user check
    await Helpers.check_user_org_validity(
        user_id=user.id, organization_id=organization_id, db=db
    )
    groups = db.query(model.NotificationGroup).filter(
                model.NotificationGroup.organization_id == organization_id
            ).all()

    if groups is None:
        raise HTTPException(detail="Organization has no notification groups",
                            status_code=status.HTTP_404_NOT_FOUND)         

    return groups


@app.get(
    "/notification-group/{group_id}", response_model=schema.NotificationGroupResponse)
async def get_notification_group(
    group_id: str,
    organization_id: str,
    user: user_schema.User = Depends(is_authenticated),
    db: orm.Session = Depends(get_db)
):
    # organization and user check
    await Helpers.check_user_org_validity(
        user_id=user.id, organization_id=organization_id, db=db
    )
    group = db.query(model.NotificationGroup).filter(
        model.NotificationGroup.id == group_id
    ).first()

    if group is None:
        raise HTTPException(detail="Notification group does not exist",
                            status_code=status.HTTP_404_NOT_FOUND)

    return group


@app.post("/notification-group", response_model=schema.NotificationGroupResponse)
async def create_notification_group(
        group: schema.NotificationGroup,
        organization_id: str,  # query_parameter
        user: user_schema.User = Depends(is_authenticated),
        db: orm.Session = Depends(get_db)):

    # organization and user check
    await Helpers.check_user_org_validity(
        user_id=user.id, organization_id=organization_id, db=db
    )

    existing_notification_group = db.query(model.NotificationGroup).filter(
        model.NotificationGroup.name == group.name
    ).first()
    if existing_notification_group is None:
        new_notification_group = model.NotificationGroup(
            id=uuid4().hex, name=group.name, organization_id=organization_id)

        db.add(new_notification_group)

        if group.members:
            for member in group.members:
                add_member = model.NotificationGroupMember(
                    id=uuid4().hex, group_id=new_notification_group.id, member_id=member)
                db.add(add_member)

        db.commit()
        db.refresh(new_notification_group)

        return new_notification_group

    return JSONResponse(
        {"message": "Notification group already exists."},
        status_code=status.HTTP_409_CONFLICT
    )


@app.put("/notification-group/{group_id}", response_model=schema.NotificationGroupResponse)
async def update_notification_group(
    group_id: str,
    organization_id: str,  # query_parameter,
    group: schema.NotificationGroupUpdate,
    user: user_schema.User = Depends(is_authenticated),
    db: orm.Session = Depends(get_db)
):

    # organization and user check
    await Helpers.check_user_org_validity(
        user_id=user.id, organization_id=organization_id, db=db
    )

    fetched_group = db.query(model.NotificationGroup).filter(
        model.NotificationGroup.id == group_id).first()
    if fetched_group is None:
        raise HTTPException(detail="Notification group does not exist",
                            status_code=status.HTTP_404_NOT_FOUND)

    if group.name:
        fetched_group.name = group.name
    if group.members:
        for member in group.members:
            member_exist = await check_group_member_exists(group_id=fetched_group.id, member_id=member, db=db)
            if member_exist:
                pass
            else:
                add_member = model.NotificationGroupMember(
                    id=uuid4().hex, group_id=fetched_group.id, member_id=member)
                db.add(add_member)

    fetched_group.last_updated = group.last_updated if group.last_updated else datetime.now()

    db.commit()
    db.refresh(fetched_group)

    return fetched_group


@app.delete("/notification-group/{group_id}")
async def delete_notification_group(
    group_id: str,
    organization_id: str,  # query_parameter,
    user: user_schema.User = Depends(is_authenticated),
    db: orm.Session = Depends(get_db)
):
    """intro-->This endpoint allows you to delete a particular notification group from the database. You need to make a delete request to the /notification-group/{notification_id} endpoint.

    paramDesc-->On delete request the url takes a query parameter "group_id" 
        param-->group_id: This is the unique identifier of the notification group

    returnDesc-->On sucessful request, it returns message,
        returnBody--> "success".
    """
    # organization and user check
    await Helpers.check_user_org_validity(
        user_id=user.id, organization_id=organization_id, db=db
    )

    group = db.query(model.NotificationGroup).filter(
        model.NotificationGroup.id == group_id).first()

    if group is None:
        raise HTTPException(detail="Notification group not found",
                            status_code=status.HTTP_404_NOT_FOUND)

    db.delete(group)
    db.commit()

    return {"message": "successfully deleted"}


@app.get(
    "/notification-group/notification-member/{group_id}",
    response_model=List[schema.NotificationGroupMemberResponse]
)
async def get_notification_group_members(
    group_id: str,
    organization_id: str,
    user: user_schema.User = Depends(is_authenticated),
    db: orm.Session = Depends(get_db)
):
    # organization and user check
    await Helpers.check_user_org_validity(
        user_id=user.id, organization_id=organization_id, db=db
    )
    group_members = db.query(model.NotificationGroupMember).filter(
        model.NotificationGroupMember.group_id == group_id
    ).all()

    return group_members


@app.post("/notification-group/notification-member", response_model=schema.NotificationGroupMemberResponse)
def add_member_to_notification_group(
    group_member: schema.NotificationGroupMember,
    user: user_schema.User = Depends(is_authenticated),
    db: orm.Session = Depends(get_db)
):

    existing_group_member = db.query(model.NotificationGroupMember).filter(
        model.NotificationGroupMember.group_id == group_member.group_id
    ).filter(model.NotificationGroupMember.member_id == group_member.member_id
             ).first()

    if existing_group_member is None:
        new_group_member = model.NotificationGroupMember(
            id=uuid4().hex, group_id=group_member.group_id, member_id=group_member.member_id
        )

        db.add(new_group_member)
        db.commit()
        db.refresh(new_group_member)

        return new_group_member

    return JSONResponse(
        {"message": "Group member already exists."},
        status_code=status.HTTP_409_CONFLICT
    )


@app.delete("/notification-group/notification-member/{group_member_id}")
def delete_notification_group(
    group_member_id: str,
    user: user_schema.User = Depends(is_authenticated),
    db: orm.Session = Depends(get_db)
):
    """intro-->This endpoint allows you to delete a particular notification group from the database. You need to make a delete request to the /notification-group/{notification_id} endpoint.

    paramDesc-->On delete request the url takes a query parameter "group_id" 
        param-->group_id: This is the unique identifier of the notification group

    returnDesc-->On sucessful request, it returns message,
        returnBody--> "success".
    """

    group_member = db.query(model.NotificationGroupMember).filter(
        model.NotificationGroupMember.id == group_member_id).first()

    if group_member is None:
        raise HTTPException(detail="Notification group member not found",
                            status_code=status.HTTP_404_NOT_FOUND)

    db.delete(group_member)
    db.commit()

    return {"message": "successfully deleted"}


@app.post("/notification-module", response_model=schema.NotificationModuleResponse)
async def create_notification_module(
        module: schema.NotificationModule,
        organization_id: str,  # query_parameter
        user: user_schema.User = Depends(is_authenticated),
        db: orm.Session = Depends(get_db)):

    # organization and user check
    await Helpers.check_user_org_validity(
        user_id=user.id, organization_id=organization_id, db=db
    )

    existing_module = db.query(model.NotificationModule).filter(
        model.NotificationModule.module_name == module.module_name
    ).first()
    if existing_module is None:
        new_module = model.NotificationModule(
            id=uuid4().hex, module_name=module.module_name, status=module.status)

        db.add(new_module)
        db.commit()
        db.refresh(new_module)

        return new_module

    return JSONResponse(
        {"message": "Notification module already exists."},
        status_code=status.HTTP_409_CONFLICT
    )


@app.put("/notification-module/{module_id}", response_model=schema.NotificationModuleResponse)
async def update_notification_module(
    module_id: str,
    organization_id: str,  # query_parameter,
    module: schema.NotificationModuleUpdate,
    user: user_schema.User = Depends(is_authenticated),
    db: orm.Session = Depends(get_db)
):

    # organization and user check
    await Helpers.check_user_org_validity(
        user_id=user.id, organization_id=organization_id, db=db
    )

    fetched_notification_module = db.query(model.NotificationModule).filter(
        model.NotificationModule.id == module_id).first()
    if fetched_notification_module is None:
        raise HTTPException(detail="Notification module does not exist",
                            status_code=status.HTTP_404_NOT_FOUND)

    if module.status != "":
        fetched_notification_module.status = module.status
    fetched_notification_module.last_updated = module.last_updated if module.last_updated else datetime.now()

    db.commit()
    db.refresh(fetched_notification_module)

    return fetched_notification_module


@app.delete("/notification-module/{module_id}")
def delete_notification_module(
    module_id: str,
    user: user_schema.User = Depends(is_authenticated),
    db: orm.Session = Depends(get_db)
):

    notification_module = db.query(model.NotificationModule).filter(
        model.NotificationModule.id == module_id).first()

    if notification_module is None:
        raise HTTPException(detail="Notification module not found",
                            status_code=status.HTTP_404_NOT_FOUND)

    db.delete(notification_module)
    db.commit()

    return {"message": "successfully deleted"}


@app.post("/notification-group-module", response_model=schema.NotificationGroupModuleResponse)
async def create_notification_group_module(
        group_module: schema.NotificationGroupModule,
        organization_id: str,  # query_parameter
        user: user_schema.User = Depends(is_authenticated),
        db: orm.Session = Depends(get_db)):

    # organization and user check
    await Helpers.check_user_org_validity(
        user_id=user.id, organization_id=organization_id, db=db
    )

    existing_group_module = db.query(model.NotificationGroupModule).filter(
        model.NotificationGroupModule.group_id == group_module.group_id
    ).filter(model.NotificationGroupModule.module_id == group_module.module_id
             ).first()

    if existing_group_module is None:
        new_group_module = model.NotificationGroupModule(
            id=uuid4().hex, group_id=group_module.group_id, module_id=group_module.module_id)

        db.add(new_group_module)
        db.commit()
        db.refresh(new_group_module)

        return new_group_module

    return JSONResponse(
        {"message": "Notification group module already exists."},
        status_code=status.HTTP_409_CONFLICT
    )


@app.delete("/notification-group-module/{group_module_id}")
def delete_notification_group_module(
    group_module_id: str,
    user: user_schema.User = Depends(is_authenticated),
    db: orm.Session = Depends(get_db)
):

    notification_group_module = db.query(model.NotificationGroupModule).filter(
        model.NotificationGroupModule.id == group_module_id).first()

    if notification_group_module is None:
        raise HTTPException(detail="Notification group module not found",
                            status_code=status.HTTP_404_NOT_FOUND)

    db.delete(notification_group_module)
    db.commit()

    return {"message": "successfully deleted"}


@app.put("/notification/{notification_id}/read", response_model=schema.Notification)
def mark_notification_read(notification_id: str, db: orm.Session = Depends(get_db)):
    """intro-->This endpoint allows you mark a queried notifications as read. To use, you need to make a put request to the /notification/{notification_id}/read enpoint. 

    paramDesc--> On put request the url takes a query parameter "notification_id" 
        param-->notification_id: This is the unique identifier of the notification

    returnDesc-->On sucessful request, it returns
        returnBody--> details of the updated notification.
    """

    notification = model.notification_selector(id=notification_id, db=db)

    if notification.has_read:
        pass
    else:
        notification.has_read = True
        notification.last_updated = datetime.utcnow()

    db.commit()
    db.refresh(notification)

    return schema.Notification.from_orm(notification)


@app.put("/notifications/read", response_model=List[schema.Notification])
def mark_notifications_read(db: orm.Session = Depends(get_db)):
    """intro-->This endpoint allows you mark all notifications as read. To use, you need to make a put request to the /notification/read enpoint. 

    returnDesc-->On sucessful request it returns 
        returnBody--> an array of the notifications.
    """

    notifications = db.query(model.Notification).all()
    for notification in notifications:
        if notification.has_read:
            pass
        else:
            notification.has_read = True
            notification.last_updated = datetime.utcnow()

        db.commit()
        db.refresh(notification)

    return list(map(schema.Notification.from_orm, notifications))


@app.put("/notifications/{notification_id}", response_model=schema.Notification)
def update_notification(notification_id: str, notification: schema.NotificationUpdate, db: orm.Session = Depends(get_db)):
    """intro-->This endpoint allows you to update a particular notification. You need to make a put request to the /notification/{notification_id} endpoint.

    paramDesc-->On put request the url takes a query parameter "notification_id" 
        param-->notification_id: This is the unique identifier of the notification
        reqBody-->content: This is the content of the notification
        reqBody-->recipient: This the receiver of the notification
        reqBody-->reference: This is a unique identifier of the notification

    returnDesc-->On sucessful request, it returns message,
        returnBody--> "success".
    """
    notification_from_db = model.notification_selector(id=notification_id, db=db)

    if notification.content != "":
        notification_from_db.content = notification.content

    if notification.reference != "":
        notification_from_db.reference = notification.reference

    if notification.recipient != "":
        notification_from_db.recipient = notification.recipient

    notification_from_db.last_updated = datetime.utcnow()

    db.commit()
    db.refresh(notification_from_db)

    return schema.Notification.from_orm(notification_from_db)


@app.delete("/notification/{notification_id}")
def delete_notification(notification_id: str, db: orm.Session = Depends(get_db)):
    """intro-->This endpoint allows you to delete a particular notification from the database. You need to make a delete request to the /notification/{notification_id} endpoint.

    paramDesc-->On delete request the url takes a query parameter "notification_id" 
        param-->notification_id: This is the unique identifier of the notification

    returnDesc-->On sucessful request, it returns message,
        returnBody--> "success".
    """

    notification = model.notification_selector(id=notification_id, db=db)

    db.delete(notification)
    db.commit()

    return {"message": "successfully deleted"}
