import grpc
import encore_pb2, encore_pb2_grpc

channel = grpc.insecure_channel("localhost:50051")
stub = encore_pb2_grpc.EncoreStub(channel)

reply = stub.ListEvents(encore_pb2.ListEventsRequest(bookable=True))
print("bookable:", [(e.title, e.seats_left) for e in reply.events])

print("watching seats on ev_101:")
for update in stub.WatchSeats(encore_pb2.GetEventRequest(event_id="ev_101")):
    print("  seats_left =", update.seats_left)
