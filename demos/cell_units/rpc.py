"""Current release RPC wire protocol over an instrument unit environment."""

from http.server import HTTPServer

from demos.cell_units.registry import VERSION

from demos.lab_cuvette_project_v1.rpc import Handler
from demos.lab_cuvette_project_release_v1.rpc import ProjectRPC


class UnitRPC(ProjectRPC):
    def dispatch(self, method, args, kwargs):
        if method == "healthz":
            return {"status": "ok", "version": VERSION}
        return super().dispatch(method, args, kwargs)

    def metadata(self):
        metadata = super().metadata()
        metadata.update(
            task="single_cell_sequencing_unit",
            version=VERSION,
            unit_id=self.environment.task.unit["id"],
            physical_baseline="cell_assets_contact_demos",
            schema="labsim.SingleCellUnit_v1.rpent_environment.v1",
        )
        return metadata


def serve(environment, port):
    rpc = UnitRPC(environment, request_log=environment.task.output / "rpc.jsonl")
    server = HTTPServer(("127.0.0.1", port), Handler)
    server.facade = rpc
    try:
        print("UNIT_RPC_READY", port, flush=True)
        while not rpc.closed:
            server.handle_request()
    finally:
        server.server_close()
        environment.close()
