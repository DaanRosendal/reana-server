# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2020 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""Status module for REANA."""

import logging
import subprocess
from datetime import datetime, timedelta

from invenio_accounts.models import SessionActivity
from reana_commons.config import (
    REANA_COMPONENT_PREFIX,
    REANA_INFRASTRUCTURE_KUBERNETES_NAMESPACE,
    REANA_RUNTIME_KUBERNETES_NAMESPACE,
    SHARED_VOLUME_PATH,
)
from reana_commons.job_utils import kubernetes_memory_to_bytes
from reana_commons.k8s.api_client import (
    current_k8s_corev1_api_client,
    current_k8s_custom_objects_api_client,
)
from reana_db.database import Session
from reana_db.models import (
    InteractiveSession,
    Job,
    JobStatus,
    Resource,
    ResourceType,
    ResourceUnit,
    RunStatus,
    User,
    UserResource,
    Workflow,
)
from reana_server.utils import get_usage_percentage
from sqlalchemy import desc


class REANAStatus:
    """REANA Status interface."""

    def __init__(self, from_=None, until=None, user=None):
        """Initialise REANAStatus class."""
        self.from_ = from_ or (datetime.now() - timedelta(days=1))
        self.until = until or datetime.now()
        self.user = user
        self.namespaces = {
            REANA_INFRASTRUCTURE_KUBERNETES_NAMESPACE,
            REANA_RUNTIME_KUBERNETES_NAMESPACE,
        }

    def execute_cmd(self, cmd):
        """Execute a command."""
        return subprocess.check_output(cmd).decode().rstrip("\r\n")

    def get_status(self):
        """Get status summary for REANA."""
        raise NotImplementedError()


class InteractiveSessionsStatus(REANAStatus):
    """Class to retrieve statistics related to REANA interactive sessions."""

    def __init__(self, from_=None, until=None, user=None):
        """Initialise InteractiveSessionsStatus class.

        :param from_: From which moment in time to collect information. Not
            implemented yet.
        :param until: Until which moment in time to collect information. Not
            implemented yet.
        :param user: A REANA-DB user model.
        :type from_: datetime
        :type until: datetime
        :type user: reana_db.models.User
        """
        super().__init__(from_=from_, until=until, user=user)

    def get_active(self):
        """Get the number of active interactive sessions."""
        non_active_statuses = [
            RunStatus.stopped,
            RunStatus.deleted,
            RunStatus.failed,
        ]
        active_interactive_sessions = (
            Session.query(InteractiveSession)
            .filter(InteractiveSession.status.notin_(non_active_statuses))
            .count()
        )
        return active_interactive_sessions

    def get_status(self):
        """Get status summary for interactive sessions."""
        return {
            "active": self.get_active(),
        }


class SystemStatus(REANAStatus):
    """Class to retrieve statistics related to the current REANA component."""

    def __init__(self, from_=None, until=None, user=None):
        """Initialise SystemStatus class.

        :param from_: From which moment in time to collect information. Not
            implemented yet.
        :param until: Until which moment in time to collect information. Not
            implemented yet.
        :param user: A REANA-DB user model.
        :type from_: datetime
        :type until: datetime
        :type user: reana_db.models.User
        """
        super().__init__(from_=from_, until=until, user=user)

    def uptime(self):
        """Get component uptime."""
        cmd = ["uptime", "-p"]
        return self.execute_cmd(cmd)

    def get_status(self):
        """Get status summary for REANA system."""
        return {
            "uptime": self.uptime(),
        }


class StorageStatus(REANAStatus):
    """Class to retrieve statistics related to REANA storage."""

    def __init__(self, from_=None, until=None, user=None):
        """Initialise StorageStatus class.

        :param from_: From which moment in time to collect information. Not
            implemented yet.
        :param until: Until which moment in time to collect information. Not
            implemented yet.
        :param user: A REANA-DB user model.
        :type from_: datetime
        :type until: datetime
        :type user: reana_db.models.User
        """
        super().__init__(from_=from_, until=until, user=user)

    def _get_path(self):
        """Retrieve the path to calculate status from."""
        path = None
        if self.user:
            path = self.user.workspace_path
        else:
            path = SHARED_VOLUME_PATH + "/users"

        return path

    def users_directory_size(self):
        """Get disk usage for users directory."""
        depth = 0
        cmd = ["du", "-h", f"--max-depth={depth}", self._get_path()]
        output = self.execute_cmd(cmd)
        size = output.split()[0]
        return size

    def shared_volume_health(self):
        """REANA shared volume health."""
        cmd = ["df", "-h", SHARED_VOLUME_PATH]
        output = self.execute_cmd(cmd).splitlines()
        headers = output[0].split()
        values = output[1].split()
        used_index = headers.index("Used")
        available_index = headers.index("Avail")
        use_percentage_index = headers.index("Use%")

        return (
            f"{values[used_index]}/{values[available_index]} "
            f"({values[use_percentage_index]})"
        )

    def get_status(self):
        """Get status summary for REANA storage."""
        return {
            "user_directory_size": self.users_directory_size(),
            "shared_volume_health": self.shared_volume_health(),
        }


class UsersStatus(REANAStatus):
    """Class to retrieve statistics related to REANA users."""

    def __init__(self, from_=None, until=None, user=None):
        """Initialise UsersStatus class.

        :param from_: From which moment in time to collect information. Not
            implemented yet.
        :param until: Until which moment in time to collect information. Not
            implemented yet.
        :param user: A REANA-DB user model.
        :type from_: datetime
        :type until: datetime
        :type user: reana_db.models.User
        """
        super().__init__(from_=from_, until=until, user=user)

    def active_web_users(self):
        """Get the number of active web users.

        Depends on how long does a session last.
        """
        return Session.query(SessionActivity).count()

    def get_status(self):
        """Get status summary for REANA users."""
        return {
            "active_web_users": self.active_web_users(),
        }


class WorkflowsStatus(REANAStatus):
    """Class to retrieve statistics related to REANA workflows."""

    def __init__(self, from_=None, until=None, user=None):
        """Initialise WorkflowsStatus class.

        :param from_: From which moment in time to collect information. Not
            implemented yet.
        :param until: Until which moment in time to collect information. Not
            implemented yet.
        :param user: A REANA-DB user model.
        :type from_: datetime
        :type until: datetime
        :type user: reana_db.models.User
        """
        super().__init__(from_=from_, until=until, user=user)

    def get_workflows_by_status(self, status):
        """Get the number of workflows in status ``status``."""
        number = Session.query(Workflow).filter(Workflow.status == status).count()

        return number

    def restarted_workflows(self):
        """Get the number of restarted workflows."""
        number = Session.query(Workflow).filter(Workflow.restart).count()

        return number

    def stuck_in_running_workflows(self):
        """Get the number of stuck running workflows."""
        inactivity_threshold = datetime.now() - timedelta(hours=12)
        number = (
            Session.query(Workflow)
            .filter(Workflow.status == RunStatus.running)
            .filter(Workflow.run_started_at <= inactivity_threshold)
            .filter(Workflow.updated <= inactivity_threshold)
            .count()
        )

        return number

    def stuck_in_pending_workflows(self):
        """Get the number of stuck pending workflows."""
        inactivity_threshold = datetime.now() - timedelta(minutes=20)
        number = (
            Session.query(Workflow)
            .filter(Workflow.status == RunStatus.pending)
            .filter(Workflow.updated <= inactivity_threshold)
            .count()
        )

        return number

    def git_workflows(self):
        """Get the number of Git based workflows."""
        number = Session.query(Workflow).filter(Workflow.git_repo != "").count()

        return number

    def get_status(self):
        """Get status summary for REANA workflows."""
        return {
            "running": self.get_workflows_by_status(RunStatus.running),
            "finished": self.get_workflows_by_status(RunStatus.finished),
            "stuck in running": self.stuck_in_running_workflows(),
            "stuck in pending": self.stuck_in_pending_workflows(),
            "queued": self.get_workflows_by_status(RunStatus.queued),
            "restarts": self.restarted_workflows(),
            "git_source": self.git_workflows(),
        }


class QuotaUsageStatus(REANAStatus):
    """Class to retrieve statistics related to the current REANA users quota usage."""

    def __init__(self, from_=None, until=None, user=None):
        """Initialise QuotaUsageStatus class.

        :param from_: From which moment in time to collect information. Not
            implemented yet.
        :param until: Until which moment in time to collect information. Not
            implemented yet.
        :param user: A REANA-DB user model.
        :type from_: datetime
        :type until: datetime
        :type user: reana_db.models.User
        """
        super().__init__(from_=from_, until=until, user=user)

    def format_user_data(self, users):
        """Format user data with human readable units."""
        return [
            {
                "email": user.user.email,
                "used": ResourceUnit.human_readable_unit(
                    user.resource.unit, user.quota_used
                ),
                "limit": ResourceUnit.human_readable_unit(
                    user.resource.unit, user.quota_limit
                ),
                "percentage": get_usage_percentage(user.quota_used, user.quota_limit),
            }
            for user in users
        ]

    def get_top_five_percentage(self, resource_type):
        """Get the top five users with highest quota usage percentage."""
        users = (
            Session.query(UserResource)
            .join(UserResource.resource)
            .filter(Resource.type_ == resource_type)
            .filter(UserResource.quota_limit != 0)
            .order_by(desc(UserResource.quota_used * 100.0 / UserResource.quota_limit))
            .limit(5)
        )
        return self.format_user_data(users)

    def get_top_five(self, resource_type):
        """Get the top five users according to quota usage."""
        users = (
            Session.query(UserResource)
            .join(UserResource.resource)
            .filter(Resource.type_ == resource_type)
            .order_by(UserResource.quota_used.desc())
            .limit(5)
        )
        return self.format_user_data(users)

    def get_status(self):
        """Get status summary for REANA quota usage."""
        return {
            "top_five_disk": self.get_top_five(ResourceType.disk),
            "top_five_cpu": self.get_top_five(ResourceType.cpu),
            "top_five_disk_percentage": self.get_top_five_percentage(ResourceType.disk),
            "top_five_cpu_percentage": self.get_top_five_percentage(ResourceType.cpu),
        }


class NodesStatus(REANAStatus):
    """Class to retrieve statistics related to REANA cluster nodes."""

    def get_nodes(self):
        """Get list of all node names."""
        nodes = current_k8s_corev1_api_client.list_node()
        return [node.metadata.name for node in nodes.items]

    def get_unschedulable_nodes(self):
        """Get list of node names that are not schedulable."""
        nodes = current_k8s_corev1_api_client.list_node(
            field_selector="spec.unschedulable=true"
        )
        return [node.metadata.name for node in nodes.items]

    def get_memory_usage(self):
        """Get nodes memory usage."""
        result = dict()
        nodes = current_k8s_corev1_api_client.list_node()
        for node in nodes.items:
            result[node.metadata.name] = {"capacity": node.status.capacity["memory"]}

        try:
            node_metrics = current_k8s_custom_objects_api_client.list_cluster_custom_object(
                "metrics.k8s.io", "v1beta1", "nodes"
            )
            for node_metric in node_metrics.get("items", []):
                node_name = node_metric["metadata"]["name"]
                result[node_name]["usage"] = node_metric["usage"]["memory"]

                node_capacity = result[node_name]["capacity"]
                node_usage = result[node_name]["usage"]
                node_usage_percentage = round(
                    kubernetes_memory_to_bytes(node_usage)
                    / kubernetes_memory_to_bytes(node_capacity)
                    * 100
                )
                result[node_name]["percentage"] = f"{node_usage_percentage}%"
        except ApiException as e:
            logging.error("Error while calling `metrics.k8s.io` API.")
            logging.error(e)
            return {}

        return result

    def get_friendly_memory_usage(self):
        """Get nodes email-friendly memory usage."""
        output_memory_usage = ""
        memory_usage = self.get_memory_usage()
        if memory_usage:
            for node, memory in memory_usage.items():
                output_memory_usage += f"\n  {node}: {memory.get('usage')}/{memory.get('capacity')} ({memory.get('percentage')})"
        return output_memory_usage

    def get_status(self):
        """Get status summary for REANA nodes."""
        return {
            "unschedulable_nodes": self.get_unschedulable_nodes(),
            "memory_usage": self.get_friendly_memory_usage(),
        }


class PodsStatus(REANAStatus):
    """Class to retrieve statistics related to REANA cluster pods."""

    def __init__(self, from_=None, until=None, user=None):
        """Initialise PodStatus class.

        :param from_: From which moment in time to collect information. Not
            implemented yet.
        :param until: Until which moment in time to collect information. Not
            implemented yet.
        :param user: A REANA-DB user model.
        :type from_: datetime
        :type until: datetime
        :type user: reana_db.models.User
        """
        self.statuses = ["Running", "Pending", "Suceeded", "Failed", "Unknown"]
        super().__init__(from_=from_, until=until, user=user)

    def get_pods_by_status(self, status, namespace):
        """Get pod name list by status."""
        pods = current_k8s_corev1_api_client.list_namespaced_pod(
            namespace, field_selector=f"status.phase={status}",
        )
        return [pod.metadata.name for pod in pods.items]

    def get_friendly_pods_by_status(self, status, namespace):
        """Get pod name list by status."""
        pods = self.get_pods_by_status(status, namespace)

        return "\n  ".join(["", *pods])

    def get_status(self):
        """Get status summary for REANA pods."""
        return {
            f"{ns}_{status.lower()}_pods": self.get_friendly_pods_by_status(status, ns)
            for ns in self.namespaces
            for status in self.statuses
        }


class JobsStatus(REANAStatus):
    """Class to retrieve statistics related to REANA cluster jobs."""

    def __init__(self, from_=None, until=None, user=None):
        """Initialise PodStatus class.

        :param from_: From which moment in time to collect information. Not
            implemented yet.
        :param until: Until which moment in time to collect information. Not
            implemented yet.
        :param user: A REANA-DB user model.
        :type from_: datetime
        :type until: datetime
        :type user: reana_db.models.User
        """
        self.compute_backends = ["Kubernetes", "HTCondor", "Slurm"]
        self.statuses = [
            JobStatus.running,
            JobStatus.finished,
            JobStatus.failed,
            JobStatus.queued,
        ]
        super().__init__(from_=from_, until=until, user=user)

    def get_jobs_by_status_and_compute_backend(self, status, compute_backend=None):
        """Get the number of jobs in status ``status`` from ``compute_backend``."""
        # number = Session.query(Job).filter(Job.status == status).count()
        query = Session.query(Job).filter(Job.status == status)
        if compute_backend:
            query = query.filter(Job.compute_backend == compute_backend)

        return query.count()

    def get_k8s_jobs_by_status(self, status):
        """Get from k8s API jobs in ``status`` status."""
        pods = current_k8s_corev1_api_client.list_namespaced_pod(
            REANA_RUNTIME_KUBERNETES_NAMESPACE, field_selector=f"status.phase={status}",
        )

        job_pods = [
            pod.metadata.name
            for pod in pods.items
            if pod.metadata.name.startswith(f"{REANA_COMPONENT_PREFIX}-run-job")
        ]

        return job_pods

    def get_status(self):
        """Get status summary for REANA jobs."""
        job_statuses = {
            compute_backend.lower(): {
                status.name: self.get_jobs_by_status_and_compute_backend(
                    status, compute_backend=compute_backend
                )
                for status in self.statuses
            }
            for compute_backend in self.compute_backends
        }

        job_statuses["kubernetes_api"] = {
            "running": len(self.get_k8s_jobs_by_status("Running")),
            "pending": len(self.get_k8s_jobs_by_status("Pending")),
        }
        return job_statuses


STATUS_OBJECT_TYPES = {
    "interactive-sessions": InteractiveSessionsStatus,
    "workflows": WorkflowsStatus,
    "users": UsersStatus,
    "system": SystemStatus,
    "storage": StorageStatus,
    "nodes": NodesStatus,
    "pods": PodsStatus,
    "jobs": JobsStatus,
    "quota-usage": QuotaUsageStatus,
}
"""High level REANA objects to extract information from."""
