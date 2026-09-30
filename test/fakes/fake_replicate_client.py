from collections import defaultdict, deque
from typing import Any, cast

from replicate.client import Client
from replicate.prediction import Prediction

from util.error_codes import DI_DEPENDENCY_NOT_MET
from util.errors import InternalError


class FakeReplicatePredictions:

    client: "FakeReplicateClient"
    responses: deque[Prediction | Exception]
    updates: dict[str, deque[Prediction | Exception]]
    requests: list[tuple[str, dict[str, Any]]]
    records: dict[str, Prediction]

    def __init__(self, client: "FakeReplicateClient"):
        self.client = client
        self.responses = deque()
        self.updates = defaultdict(deque)
        self.requests = []
        self.records = {}

    def create(self, **kwargs: Any) -> Prediction:
        self.requests.append(("create", kwargs))
        if not self.responses:
            raise InternalError("No Replicate prediction configured", DI_DEPENDENCY_NOT_MET)
        prediction = self.responses.popleft()
        if isinstance(prediction, Exception):
            raise prediction
        prediction = prediction.copy(deep = True)
        # keep the SDK's wait/reload/cancel behavior real while replacing its transport
        prediction._client = cast(Client, self.client)
        self.records[prediction.id] = prediction
        return prediction

    def get(self, id: str) -> Prediction:
        self.requests.append(("get", {"id": id}))
        if not self.updates[id]:
            raise InternalError(f"No Replicate update configured: {id}", DI_DEPENDENCY_NOT_MET)
        prediction = self.updates[id].popleft()
        if isinstance(prediction, Exception):
            raise prediction
        self.records[id] = prediction
        return prediction.copy(deep = True)

    def cancel(self, id: str) -> Prediction:
        self.requests.append(("cancel", {"id": id}))
        prediction = self.records[id].copy(update = {"status": "canceled"})
        self.records[id] = prediction
        return prediction


class FakeReplicateClient:

    predictions: FakeReplicatePredictions
    poll_interval: float = 0

    def __init__(self):
        self.predictions = FakeReplicatePredictions(self)
