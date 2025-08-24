from aiohttp import web
from util.config import Config


def create_api(bot):
    routes = web.RouteTableDef()

    @routes.post('/order_placed')
    async def order_placed(request: web.Request):
        body = await request.json()
        
        # If SQS is enabled, send to queue instead of processing directly
        if Config.ENABLE_SQS and bot.sqs_manager:
            success = await bot.sqs_manager.send_order_placed(body)
            if success:
                return web.json_response(
                    data=dict(
                        result=dict(
                            message="Order placed event queued successfully",
                            queued=True
                        )
                    )
                )
            else:
                return web.json_response(
                    data=dict(
                        result=dict(
                            error="Failed to queue order placed event",
                            queued=False
                        )
                    ),
                    status=500
                )
        else:
            # Fallback to direct processing
            return web.json_response(
                data=dict(
                    result=await bot.order_placed(body)
                )
            )

    @routes.post('/order_assigned')
    async def order_assigned(request: web.Request):
        body = await request.json()
        
        # If SQS is enabled, send to queue instead of processing directly
        if Config.ENABLE_SQS and bot.sqs_manager:
            success = await bot.sqs_manager.send_order_assigned(body)
            if success:
                return web.json_response(
                    data=dict(
                        result=dict(
                            message="Order assigned event queued successfully",
                            queued=True
                        )
                    )
                )
            else:
                return web.json_response(
                    data=dict(
                        result=dict(
                            error="Failed to queue order assigned event",
                            queued=False
                        )
                    ),
                    status=500
                )
        else:
            # Fallback to direct processing
            return web.json_response(
                data=dict(
                    result=await bot.add_to_thread(
                        body.get('server_id'),
                        body.get('thread_id'),
                        body.get('members'),
                        body.get('order'),
                    )
                )
            )

    @routes.post('/order_status_updated')
    async def order_status_updated(request: web.Request):
        body = await request.json()
        
        # If SQS is enabled, send to queue instead of processing directly
        if Config.ENABLE_SQS and bot.sqs_manager:
            success = await bot.sqs_manager.send_order_status_updated(body)
            if success:
                return web.json_response(
                    data=dict(
                        result=dict(
                            message="Order status updated event queued successfully",
                            queued=True
                        )
                    )
                )
            else:
                return web.json_response(
                    data=dict(
                        result=dict(
                            error="Failed to queue order status updated event",
                            queued=False
                        )
                    ),
                    status=500
                )
        else:
            # Fallback to direct processing
            return web.json_response(
                data=dict(
                    result=await bot.order_status_update(
                        body.get('order'),
                    )
                )
            )

    app = web.Application()
    app.add_routes(routes)

    return app
