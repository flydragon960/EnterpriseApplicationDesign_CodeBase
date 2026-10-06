# gRPC server for the Encore contract.
import time
from concurrent import futures
import grpc
import encore_pb2, encore_pb2_grpc

EVENTS = [
    encore_pb2.Event(id="ev_101", title="Jazz Ensemble: Fall Concert", seats_left=42),
    encore_pb2.Event(id="ev_102", title="Improv Night", seats_left=0),
]

class EncoreService(encore_pb2_grpc.EncoreServicer):
    def ListEvents(self, request, context):
        evs = [e for e in EVENTS if not request.bookable or e.seats_left > 0]
        return encore_pb2.ListEventsReply(events=evs)

    def GetEvent(self, request, context):
        for e in EVENTS:
            if e.id == request.event_id:
                return e
        context.abort(grpc.StatusCode.NOT_FOUND, "not_found")

    def WatchSeats(self, request, context):
        for left in (42, 41, 40):          # three updates, pushed by the server
            yield encore_pb2.SeatUpdate(event_id=request.event_id, seats_left=left)
            time.sleep(0.1)

server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
encore_pb2_grpc.add_EncoreServicer_to_server(EncoreService(), server)
server.add_insecure_port("localhost:50051")
server.start()
server.wait_for_termination()
