#![allow(clippy::useless_conversion)]

use camino::Utf8Path;
use ccb_jobs::models::{JobRecord, MessageEnvelope};
use ccb_mailbox::kernel::Clock;
use ccb_mailbox::{InboundEventStatus, InboundEventType, MailboxKernelService, MailboxRecord};
use ccb_message_bureau::{MessageBureauControlService, MessageBureauFacade};
use ccb_storage::paths::PathLayout;
use pyo3::exceptions::{PyOSError, PyRuntimeError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::{PyAny, PyDict, PyList};
use serde_json::Value;
use std::sync::Arc;

// ---------------------------------------------------------------------------
// JSON conversion helpers (serde_json::Value <-> Python object via json.loads)
// ---------------------------------------------------------------------------

fn serde_value_to_pyobject(py: Python<'_>, value: &Value) -> PyResult<Py<PyAny>> {
    let json_str = serde_json::to_string(value).map_err(|e| {
        PyErr::new::<PyRuntimeError, _>(format!("serialization failed: {e}"))
    })?;
    let module = py.import_bound("json")?;
    let loads = module.getattr("loads")?;
    let obj = loads.call1((json_str,))?;
    Ok(obj.unbind())
}

fn pyobject_to_serde_value(obj: &Bound<'_, PyAny>) -> PyResult<Value> {
    let py = obj.py();
    let module = py.import_bound("json")?;
    let dumps = module.getattr("dumps")?;
    let json_str = dumps.call1((obj,))?.extract::<String>()?;
    serde_json::from_str(&json_str)
        .map_err(|e| PyErr::new::<PyValueError, _>(format!("invalid JSON: {e}")))
}

fn to_py_object<T: serde::Serialize>(py: Python<'_>, value: T) -> PyResult<Py<PyAny>> {
    let v = serde_json::to_value(value).map_err(|e| {
        PyErr::new::<PyRuntimeError, _>(format!("serialization failed: {e}"))
    })?;
    serde_value_to_pyobject(py, &v)
}

fn option_to_py_object<T: serde::Serialize>(
    py: Python<'_>,
    value: Option<T>,
) -> PyResult<Py<PyAny>> {
    match value {
        Some(v) => to_py_object(py, v),
        None => Ok(py.None()),
    }
}

// ---------------------------------------------------------------------------
// Error conversion
// ---------------------------------------------------------------------------

fn mailbox_error_to_pyerr(e: ccb_mailbox::MailboxError) -> PyErr {
    match e {
        ccb_mailbox::MailboxError::Storage(_) | ccb_mailbox::MailboxError::Io(_) => {
            PyErr::new::<PyOSError, _>(e.to_string())
        }
        ccb_mailbox::MailboxError::Json(_) => PyErr::new::<PyValueError, _>(e.to_string()),
        ccb_mailbox::MailboxError::NotFound(_) => PyErr::new::<PyRuntimeError, _>(e.to_string()),
    }
}

// ---------------------------------------------------------------------------
// mailbox_kernel submodule
// ---------------------------------------------------------------------------

#[pyclass(name = "InboundEventType", eq, eq_int, frozen)]
#[derive(Clone, Copy, PartialEq)]
pub enum PyInboundEventType {
    TaskRequest,
    TaskReply,
    CompletionNotice,
    RetrySignal,
    SystemSignal,
    BarrierRelease,
}

fn inbound_event_type_from_int(value: u32) -> PyResult<InboundEventType> {
    match value {
        0 => Ok(InboundEventType::TaskRequest),
        1 => Ok(InboundEventType::TaskReply),
        2 => Ok(InboundEventType::CompletionNotice),
        3 => Ok(InboundEventType::RetrySignal),
        4 => Ok(InboundEventType::SystemSignal),
        5 => Ok(InboundEventType::BarrierRelease),
        _ => Err(PyErr::new::<PyValueError, _>(format!(
            "invalid InboundEventType discriminant: {value}"
        ))),
    }
}

fn option_inbound_event_type_from_int(
    value: Option<u32>,
) -> PyResult<Option<InboundEventType>> {
    match value {
        None => Ok(None),
        Some(v) => Ok(Some(inbound_event_type_from_int(v)?)),
    }
}

#[pyclass(name = "InboundEventStatus", eq, eq_int, frozen)]
#[derive(Clone, Copy, PartialEq)]
pub enum PyInboundEventStatus {
    Created,
    Queued,
    Delivering,
    Consumed,
    Superseded,
    Abandoned,
}

fn inbound_event_status_from_int(value: u32) -> PyResult<InboundEventStatus> {
    match value {
        0 => Ok(InboundEventStatus::Created),
        1 => Ok(InboundEventStatus::Queued),
        2 => Ok(InboundEventStatus::Delivering),
        3 => Ok(InboundEventStatus::Consumed),
        4 => Ok(InboundEventStatus::Superseded),
        5 => Ok(InboundEventStatus::Abandoned),
        _ => Err(PyErr::new::<PyValueError, _>(format!(
            "invalid InboundEventStatus discriminant: {value}"
        ))),
    }
}

#[pyclass(name = "MailboxState", eq, eq_int, frozen)]
#[derive(Clone, Copy, PartialEq)]
pub enum PyMailboxState {
    Idle,
    Delivering,
    Blocked,
    Recovering,
    Degraded,
}

#[pyclass(name = "LeaseState", eq, eq_int, frozen)]
#[derive(Clone, Copy, PartialEq)]
pub enum PyLeaseState {
    Acquired,
    Released,
    Expired,
    Orphaned,
}

#[pyclass(name = "MailboxKernelService")]
pub struct PyMailboxKernelService {
    inner: MailboxKernelService,
}

#[pymethods]
impl PyMailboxKernelService {
    #[new]
    fn new(root_path: &str) -> PyResult<Self> {
        let path = Utf8Path::new(root_path);
        let layout = PathLayout::new(path);
        Ok(Self {
            inner: MailboxKernelService::new(layout),
        })
    }

    fn latest_events(&self, py: Python<'_>, agent_name: &str) -> PyResult<Py<PyAny>> {
        let records = self.inner.latest_events(agent_name);
        to_py_object(py, records)
    }

    #[pyo3(signature = (agent_name, event_type=None))]
    fn pending_events(
        &self,
        py: Python<'_>,
        agent_name: &str,
        event_type: Option<u32>,
    ) -> PyResult<Py<PyAny>> {
        let event_type = option_inbound_event_type_from_int(event_type)?;
        let records = self.inner.pending_events(agent_name, event_type);
        to_py_object(py, records)
    }

    fn head_pending_event(&self, py: Python<'_>, agent_name: &str) -> PyResult<Py<PyAny>> {
        let record = self.inner.head_pending_event(agent_name);
        option_to_py_object(py, record)
    }

    #[pyo3(signature = (agent_name, event_type=None))]
    fn peek_next(
        &self,
        py: Python<'_>,
        agent_name: &str,
        event_type: Option<u32>,
    ) -> PyResult<Py<PyAny>> {
        let event_type = option_inbound_event_type_from_int(event_type)?;
        let record = self.inner.peek_next(agent_name, event_type);
        option_to_py_object(py, record)
    }

    #[pyo3(signature = (agent_name, inbound_event_id, started_at=None))]
    fn claim(
        &self,
        py: Python<'_>,
        agent_name: &str,
        inbound_event_id: &str,
        started_at: Option<&str>,
    ) -> PyResult<Py<PyAny>> {
        let record = self.inner.claim(agent_name, inbound_event_id, started_at);
        option_to_py_object(py, record)
    }

    #[pyo3(signature = (agent_name, event_type=None, started_at=None))]
    fn claim_next(
        &self,
        py: Python<'_>,
        agent_name: &str,
        event_type: Option<u32>,
        started_at: Option<&str>,
    ) -> PyResult<Py<PyAny>> {
        let event_type = option_inbound_event_type_from_int(event_type)?;
        let record = self.inner.claim_next(agent_name, event_type, started_at);
        option_to_py_object(py, record)
    }

    #[pyo3(signature = (agent_name, inbound_event_id, finished_at=None))]
    fn consume(
        &self,
        py: Python<'_>,
        agent_name: &str,
        inbound_event_id: &str,
        finished_at: Option<&str>,
    ) -> PyResult<Py<PyAny>> {
        let record = self.inner.consume(agent_name, inbound_event_id, finished_at);
        option_to_py_object(py, record)
    }

    #[pyo3(signature = (agent_name, inbound_event_id, finished_at=None))]
    fn abandon(
        &self,
        py: Python<'_>,
        agent_name: &str,
        inbound_event_id: &str,
        finished_at: Option<&str>,
    ) -> PyResult<Py<PyAny>> {
        let record = self.inner.abandon(agent_name, inbound_event_id, finished_at);
        option_to_py_object(py, record)
    }

    #[pyo3(signature = (agent_name, inbound_event_id, finished_at=None))]
    fn supersede(
        &self,
        py: Python<'_>,
        agent_name: &str,
        inbound_event_id: &str,
        finished_at: Option<&str>,
    ) -> PyResult<Py<PyAny>> {
        let record = self.inner.supersede(agent_name, inbound_event_id, finished_at);
        option_to_py_object(py, record)
    }

    #[pyo3(signature = (agent_name, inbound_event_id, started_at=None, finished_at=None))]
    #[allow(clippy::too_many_arguments)]
    fn ack_reply(
        &self,
        py: Python<'_>,
        agent_name: &str,
        inbound_event_id: &str,
        started_at: Option<&str>,
        finished_at: Option<&str>,
    ) -> PyResult<Py<PyAny>> {
        let record = self.inner.ack_reply(agent_name, inbound_event_id, started_at, finished_at);
        option_to_py_object(py, record)
    }

    #[pyo3(signature = (agent_name, inbound_event_id, status, finished_at=None))]
    fn mark_terminal(
        &self,
        py: Python<'_>,
        agent_name: &str,
        inbound_event_id: &str,
        status: u32,
        finished_at: Option<&str>,
    ) -> PyResult<Py<PyAny>> {
        let status = inbound_event_status_from_int(status)?;
        let record = self.inner.mark_terminal(agent_name, inbound_event_id, status, finished_at);
        option_to_py_object(py, record)
    }

    #[pyo3(signature = (agent_name, updated_at=None))]
    fn rebuild_mailbox_summary(
        &self,
        py: Python<'_>,
        agent_name: &str,
        updated_at: Option<&str>,
    ) -> PyResult<Py<PyAny>> {
        let record = self
            .inner
            .rebuild_mailbox_summary(agent_name, updated_at)
            .map_err(mailbox_error_to_pyerr)?;
        to_py_object(py, record)
    }

    #[pyo3(signature = (agent_name, updated_at=None, prior=None, summary_source="projection"))]
    fn project_mailbox_summary(
        &self,
        py: Python<'_>,
        agent_name: &str,
        updated_at: Option<&str>,
        prior: Option<&Bound<'_, PyDict>>,
        summary_source: &str,
    ) -> PyResult<Py<PyAny>> {
        let prior_record: Option<MailboxRecord> = match prior {
            None => None,
            Some(dict) => {
                let value = pyobject_to_serde_value(dict.as_any())?;
                Some(serde_json::from_value(value).map_err(|e| {
                    PyErr::new::<PyValueError, _>(format!("invalid prior summary: {e}"))
                })?)
            }
        };
        let record = self
            .inner
            .project_mailbox_summary(agent_name, updated_at, prior_record.as_ref(), summary_source)
            .map_err(mailbox_error_to_pyerr)?;
        to_py_object(py, record)
    }

    #[pyo3(signature = (agent_name, updated_at=None))]
    fn refresh_mailbox(
        &self,
        py: Python<'_>,
        agent_name: &str,
        updated_at: Option<&str>,
    ) -> PyResult<Py<PyAny>> {
        let record = self
            .inner
            .refresh_mailbox(agent_name, updated_at)
            .map_err(mailbox_error_to_pyerr)?;
        to_py_object(py, record)
    }
}

// ---------------------------------------------------------------------------
// message_bureau submodule
// ---------------------------------------------------------------------------

#[pyclass(name = "MessageState", eq, eq_int, frozen)]
#[derive(Clone, Copy, PartialEq)]
pub enum PyMessageState {
    Created,
    Queued,
    Dispatching,
    Running,
    PartiallyReplied,
    Completed,
    Incomplete,
    Failed,
    Cancelled,
    DeadLetter,
}

#[pyclass(name = "AttemptState", eq, eq_int, frozen)]
#[derive(Clone, Copy, PartialEq)]
pub enum PyAttemptState {
    Pending,
    Delivering,
    Running,
    WaitingCompletion,
    ReplyReady,
    Stalled,
    RuntimeDead,
    Failed,
    Incomplete,
    Cancelled,
    Superseded,
    DeadLetter,
    Completed,
}

#[pyclass(name = "ReplyTerminalStatus", eq, eq_int, frozen)]
#[derive(Clone, Copy, PartialEq)]
pub enum PyReplyTerminalStatus {
    Completed,
    Incomplete,
    Failed,
    Cancelled,
}

#[pyclass(name = "CallbackEdgeState", eq, eq_int, frozen)]
#[derive(Clone, Copy, PartialEq)]
pub enum PyCallbackEdgeState {
    Pending,
    ChildCompleted,
    ContinuationSubmitted,
    Done,
    Failed,
    TimedOut,
}

fn default_clock() -> Clock {
    Arc::new(|| {
        chrono::Utc::now()
            .to_rfc3339_opts(chrono::SecondsFormat::Secs, true)
            .replace("+00:00", "Z")
    })
}

fn optional_config_value(config: Option<&Bound<'_, PyAny>>) -> PyResult<Option<Value>> {
    match config {
        None => Ok(None),
        Some(obj) => {
            let value = pyobject_to_serde_value(obj)?;
            Ok(Some(value))
        }
    }
}

#[pyclass(name = "MessageBureauFacade")]
pub struct PyMessageBureauFacade {
    inner: MessageBureauFacade,
}

#[pymethods]
impl PyMessageBureauFacade {
    #[new]
    #[pyo3(signature = (root_path, config=None))]
    fn new(root_path: &str, config: Option<&Bound<'_, PyAny>>) -> PyResult<Self> {
        let path = Utf8Path::new(root_path);
        let layout = PathLayout::new(path);
        let config = optional_config_value(config)?;
        Ok(Self {
            inner: MessageBureauFacade::new(layout, config, default_clock()),
        })
    }

    #[pyo3(signature = (request, jobs, accepted_at, submission_id=None, origin_message_id=None))]
    fn record_submission(
        &self,
        request: &Bound<'_, PyAny>,
        jobs: &Bound<'_, PyAny>,
        accepted_at: &str,
        submission_id: Option<&str>,
        origin_message_id: Option<&str>,
    ) -> PyResult<Option<String>> {
        let request_value = pyobject_to_serde_value(request)?;
        let request_envelope: MessageEnvelope = serde_json::from_value(request_value).map_err(
            |e| PyErr::new::<PyValueError, _>(format!("invalid request envelope: {e}")),
        )?;

        let jobs_list = jobs.downcast::<PyList>().map_err(|_| {
            PyErr::new::<PyValueError, _>("jobs must be a list of dicts".to_string())
        })?;
        let mut job_records = Vec::with_capacity(jobs_list.len());
        for item in jobs_list.iter() {
            let value = pyobject_to_serde_value(&item)?;
            let job: JobRecord = serde_json::from_value(value).map_err(|e| {
                PyErr::new::<PyValueError, _>(format!("invalid job record: {e}"))
            })?;
            job_records.push(job);
        }

        Ok(self.inner.record_submission(
            &request_envelope,
            &job_records,
            submission_id,
            accepted_at,
            origin_message_id,
        ))
    }

    fn claimable_request_job_ids(&self, agent_name: &str) -> Vec<String> {
        self.inner.claimable_request_job_ids(agent_name)
    }

    fn get_message(&self, py: Python<'_>, message_id: &str) -> PyResult<Py<PyAny>> {
        let record = self.inner.get_message(message_id);
        option_to_py_object(py, record)
    }

    fn all_messages(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let records = self.inner.all_messages();
        to_py_object(py, records)
    }
}

#[pyclass(name = "MessageBureauControlService")]
pub struct PyMessageBureauControlService {
    inner: MessageBureauControlService,
}

#[pymethods]
impl PyMessageBureauControlService {
    #[new]
    #[pyo3(signature = (root_path, config=None))]
    fn new(root_path: &str, config: Option<&Bound<'_, PyAny>>) -> PyResult<Self> {
        let path = Utf8Path::new(root_path);
        let layout = PathLayout::new(path);
        let config = optional_config_value(config)?;
        Ok(Self {
            inner: MessageBureauControlService::new(layout, config, None),
        })
    }

    #[pyo3(signature = (target, detail=None))]
    fn queue_summary(
        &self,
        py: Python<'_>,
        target: &str,
        detail: Option<bool>,
    ) -> PyResult<Py<PyAny>> {
        let value = self.inner.queue_summary(target, detail);
        serde_value_to_pyobject(py, &value)
    }

    fn agent_queue(&self, py: Python<'_>, agent_name: &str) -> PyResult<Py<PyAny>> {
        let value = self.inner.agent_queue(agent_name);
        serde_value_to_pyobject(py, &value)
    }

    fn trace(&self, py: Python<'_>, target: &str) -> PyResult<Py<PyAny>> {
        let value = self.inner.trace(target);
        serde_value_to_pyobject(py, &value)
    }

    #[pyo3(signature = (agent_name, detail=None))]
    fn inbox(
        &self,
        py: Python<'_>,
        agent_name: &str,
        detail: Option<bool>,
    ) -> PyResult<Py<PyAny>> {
        let value = self.inner.inbox(agent_name, detail);
        serde_value_to_pyobject(py, &value)
    }

    fn mailbox_head(&self, py: Python<'_>, agent_name: &str) -> PyResult<Py<PyAny>> {
        let value = self.inner.mailbox_head(agent_name);
        serde_value_to_pyobject(py, &value)
    }
}

// ---------------------------------------------------------------------------
// Module entrypoint
// ---------------------------------------------------------------------------

#[pymodule]
fn ccb_py_mailbox(m: &Bound<'_, PyModule>) -> PyResult<()> {
    let py = m.py();

    // Mark the extension module as a package so `import ccb_py_mailbox.X`
    // resolves to the submodules registered below.
    m.add("__path__", vec!["".to_string()])?;

    let mailbox_kernel = PyModule::new_bound(py, "mailbox_kernel")?;
    mailbox_kernel.add_class::<PyInboundEventType>()?;
    mailbox_kernel.add_class::<PyInboundEventStatus>()?;
    mailbox_kernel.add_class::<PyMailboxState>()?;
    mailbox_kernel.add_class::<PyLeaseState>()?;
    mailbox_kernel.add_class::<PyMailboxKernelService>()?;
    mailbox_kernel.add("SCHEMA_VERSION", ccb_mailbox::SCHEMA_VERSION)?;
    m.add_submodule(&mailbox_kernel)?;

    let message_bureau = PyModule::new_bound(py, "message_bureau")?;
    message_bureau.add_class::<PyMessageState>()?;
    message_bureau.add_class::<PyAttemptState>()?;
    message_bureau.add_class::<PyReplyTerminalStatus>()?;
    message_bureau.add_class::<PyCallbackEdgeState>()?;
    message_bureau.add_class::<PyMessageBureauFacade>()?;
    message_bureau.add_class::<PyMessageBureauControlService>()?;
    message_bureau.add("SCHEMA_VERSION", ccb_message_bureau::SCHEMA_VERSION)?;
    m.add_submodule(&message_bureau)?;

    // Register the submodules in sys.modules so dotted imports work.
    let sys = py.import_bound("sys")?;
    let modules = sys.getattr("modules")?;
    modules.set_item("ccb_py_mailbox.mailbox_kernel", &mailbox_kernel)?;
    modules.set_item("ccb_py_mailbox.message_bureau", &message_bureau)?;

    Ok(())
}
