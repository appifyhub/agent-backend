from collections import defaultdict, deque
from typing import Any

from replicate.types import Prediction

from util.error_codes import DI_DEPENDENCY_NOT_MET
from util.errors import InternalError

TERMINAL_PREDICTION_STATUSES = {"succeeded", "failed", "canceled"}


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
        self.records[prediction.id] = prediction
        return prediction.model_copy(deep = True)

    def get(self, prediction_id: str) -> Prediction:
        self.requests.append(("get", {"prediction_id": prediction_id}))
        if not self.updates[prediction_id]:
            # a finished prediction no longer changes, so unconfigured polls observe its last state
            recorded = self.records.get(prediction_id)
            if recorded is not None and recorded.status in TERMINAL_PREDICTION_STATUSES:
                return recorded.model_copy(deep = True)
            raise InternalError(f"No Replicate update configured: {prediction_id}", DI_DEPENDENCY_NOT_MET)
        prediction = self.updates[prediction_id].popleft()
        if isinstance(prediction, Exception):
            raise prediction
        self.records[prediction_id] = prediction
        return prediction.model_copy(deep = True)

    def wait(self, prediction_id: str) -> Prediction:
        self.requests.append(("wait", {"prediction_id": prediction_id}))
        # mirrors the SDK: poll by id until the prediction reaches a terminal status
        prediction = self.get(prediction_id = prediction_id)
        while prediction.status not in TERMINAL_PREDICTION_STATUSES:
            prediction = self.get(prediction_id = prediction.id)
        return prediction

    def cancel(self, prediction_id: str) -> Prediction:
        self.requests.append(("cancel", {"prediction_id": prediction_id}))
        prediction = self.records[prediction_id].model_copy(update = {"status": "canceled"})
        self.records[prediction_id] = prediction
        return prediction.model_copy(deep = True)


class FakeReplicateClient:

    predictions: FakeReplicatePredictions
    poll_interval: float = 0

    def __init__(self):
        self.predictions = FakeReplicatePredictions(self)
