import os
import tkinter as tk
from tkinter import messagebox

from PIL import (
    Image,
    ImageTk
)

from core.evidence_lifecycle import (
    EVIDENCE_DIR,
    cleanup_evidence,
    get_evidence,
    list_evidence,
    mark_presented
)

from core.evidence_owner import (
    owner_acknowledge_evidence,
    owner_delete_evidence,
    owner_keep_evidence
)


# ============================================================
# SENTINEL PHOENIX
# VISUAL EVIDENCE VIEWER V1
#
# Displays UNKNOWN-person evidence locally.
#
# OWNER actions:
# - KEEP
# - DELETE
# - ACKNOWLEDGE
#
# Sensitive actions remain protected by:
#
# OWNER FACE
#       +
# ACTIVE LIVENESS
# ============================================================


VIEWER_VERSION = "1.0"

WINDOW_TITLE = (
    "Sentinel Phoenix - Security Evidence"
)

WINDOW_WIDTH = 1050

WINDOW_HEIGHT = 700


# ============================================================
# DATA HELPERS
# ============================================================

def latest_evidence():

    records = list_evidence()

    if not records:

        return None

    return records[0]


def evidence_path(
    record
):

    if not record:

        return None

    filename = record.get(
        "filename"
    )

    if not filename:

        return None

    return os.path.join(
        EVIDENCE_DIR,
        filename
    )


# ============================================================
# APPLICATION
# ============================================================

class EvidenceViewer:

    def __init__(
        self,
        root
    ):

        self.root = root

        self.root.title(
            WINDOW_TITLE
        )

        self.root.geometry(
            f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}"
        )

        self.root.minsize(
            850,
            580
        )

        self.current_record = None

        self.current_photo = None

        self._build_ui()

        self.refresh()


    # ========================================================
    # UI
    # ========================================================

    def _build_ui(
        self
    ):

        self.root.configure(
            bg="#080b10"
        )


        # ====================================================
        # HEADER
        # ====================================================

        header = tk.Frame(
            self.root,
            bg="#080b10"
        )

        header.pack(
            fill="x",
            padx=25,
            pady=20
        )


        title = tk.Label(
            header,
            text="SENTINEL PHOENIX",
            font=(
                "Arial",
                20,
                "bold"
            ),
            fg="#f4f7fb",
            bg="#080b10"
        )

        title.pack(
            anchor="w"
        )


        subtitle = tk.Label(
            header,
            text=(
                "UNKNOWN PERSON / "
                "SECURITY EVIDENCE REVIEW"
            ),
            font=(
                "Arial",
                11
            ),
            fg="#8fa3b8",
            bg="#080b10"
        )

        subtitle.pack(
            anchor="w",
            pady=(
                4,
                0
            )
        )


        # ====================================================
        # CONTENT
        # ====================================================

        content = tk.Frame(
            self.root,
            bg="#080b10"
        )

        content.pack(
            fill="both",
            expand=True,
            padx=25,
            pady=(
                0,
                15
            )
        )


        # ====================================================
        # IMAGE PANEL
        # ====================================================

        self.image_panel = tk.Frame(
            content,
            bg="#101722",
            bd=1,
            relief="solid"
        )

        self.image_panel.pack(
            side="left",
            fill="both",
            expand=True,
            padx=(
                0,
                15
            )
        )


        self.image_label = tk.Label(
            self.image_panel,
            text="NO EVIDENCE",
            font=(
                "Arial",
                18,
                "bold"
            ),
            fg="#8291a3",
            bg="#101722"
        )

        self.image_label.pack(
            fill="both",
            expand=True,
            padx=15,
            pady=15
        )


        # ====================================================
        # INFORMATION PANEL
        # ====================================================

        side = tk.Frame(
            content,
            width=320,
            bg="#101722",
            bd=1,
            relief="solid"
        )

        side.pack(
            side="right",
            fill="y"
        )

        side.pack_propagate(
            False
        )


        info_title = tk.Label(
            side,
            text="INCIDENT INFORMATION",
            font=(
                "Arial",
                13,
                "bold"
            ),
            fg="#ffffff",
            bg="#101722"
        )

        info_title.pack(
            anchor="w",
            padx=20,
            pady=(
                20,
                15
            )
        )


        self.info_label = tk.Label(
            side,
            text="",
            justify="left",
            anchor="nw",
            wraplength=275,
            font=(
                "Arial",
                10
            ),
            fg="#c9d3df",
            bg="#101722"
        )

        self.info_label.pack(
            fill="x",
            padx=20
        )


        # ====================================================
        # SECURITY STATUS
        # ====================================================

        self.security_label = tk.Label(
            side,
            text=(
                "\nSECURITY POLICY\n"
                "OWNER verification required\n"
                "Active liveness required\n"
                "Biometric processing: LOCAL"
            ),
            justify="left",
            anchor="w",
            font=(
                "Arial",
                9
            ),
            fg="#7f93a8",
            bg="#101722"
        )

        self.security_label.pack(
            fill="x",
            padx=20,
            pady=(
                15,
                10
            )
        )


        # ====================================================
        # ACTION BUTTONS
        # ====================================================

        button_frame = tk.Frame(
            side,
            bg="#101722"
        )

        button_frame.pack(
            side="bottom",
            fill="x",
            padx=20,
            pady=20
        )


        self.keep_button = tk.Button(
            button_frame,
            text="KEEP",
            command=self.keep_current,
            height=2
        )

        self.keep_button.pack(
            fill="x",
            pady=4
        )


        self.ack_button = tk.Button(
            button_frame,
            text="ACKNOWLEDGE",
            command=self.acknowledge_current,
            height=2
        )

        self.ack_button.pack(
            fill="x",
            pady=4
        )


        self.delete_button = tk.Button(
            button_frame,
            text="DELETE",
            command=self.delete_current,
            height=2
        )

        self.delete_button.pack(
            fill="x",
            pady=4
        )


        self.refresh_button = tk.Button(
            button_frame,
            text="REFRESH",
            command=self.refresh
        )

        self.refresh_button.pack(
            fill="x",
            pady=(
                15,
                4
            )
        )


        close_button = tk.Button(
            button_frame,
            text="CLOSE",
            command=self.root.destroy
        )

        close_button.pack(
            fill="x",
            pady=4
        )


    # ========================================================
    # ENABLE / DISABLE ACTIONS
    # ========================================================

    def _set_actions_enabled(
        self,
        enabled
    ):

        state = (
            "normal"
            if enabled
            else
            "disabled"
        )

        self.keep_button.configure(
            state=state
        )

        self.ack_button.configure(
            state=state
        )

        self.delete_button.configure(
            state=state
        )


    # ========================================================
    # LOAD IMAGE
    # ========================================================

    def _load_image(
        self,
        path
    ):

        if (
            not path
            or
            not os.path.isfile(
                path
            )
        ):

            self.current_photo = None

            self.image_label.configure(
                image="",
                text="EVIDENCE IMAGE NOT AVAILABLE"
            )

            return


        try:

            image = Image.open(
                path
            )

            image.thumbnail(
                (
                    650,
                    580
                )
            )

            self.current_photo = (
                ImageTk.PhotoImage(
                    image
                )
            )


            self.image_label.configure(
                image=self.current_photo,
                text=""
            )


        except Exception as error:

            self.current_photo = None

            self.image_label.configure(
                image="",
                text=(
                    "IMAGE LOAD ERROR\n\n"
                    +
                    str(
                        error
                    )
                )
            )


    # ========================================================
    # INFORMATION
    # ========================================================

    def _show_information(
        self,
        record
    ):

        if not record:

            self.info_label.configure(
                text=(
                    "No UNKNOWN-person "
                    "evidence is currently available."
                )
            )

            return


        evidence_id = record.get(
            "id",
            "UNKNOWN"
        )

        state = record.get(
            "state",
            "UNKNOWN"
        )

        source = record.get(
            "source",
            "UNKNOWN_PERSON"
        )

        created = record.get(
            "created_at_iso",
            "UNKNOWN"
        )

        kept = (
            "YES"
            if record.get(
                "kept"
            )
            else
            "NO"
        )

        presented = (
            "YES"
            if record.get(
                "presented"
            )
            else
            "NO"
        )

        acknowledged = (
            "YES"
            if record.get(
                "acknowledged"
            )
            else
            "NO"
        )


        metadata = record.get(
            "metadata",
            {}
        )


        text = (
            f"EVIDENCE ID\n"
            f"{evidence_id}\n\n"

            f"TYPE\n"
            f"{source}\n\n"

            f"STATE\n"
            f"{state}\n\n"

            f"DATE / TIME\n"
            f"{created}\n\n"

            f"KEPT\n"
            f"{kept}\n\n"

            f"PRESENTED\n"
            f"{presented}\n\n"

            f"ACKNOWLEDGED\n"
            f"{acknowledged}"
        )


        if metadata:

            text += (
                "\n\nMETADATA\n"
            )

            for key, value in metadata.items():

                text += (
                    f"{key}: {value}\n"
                )


        self.info_label.configure(
            text=text
        )


    # ========================================================
    # REFRESH
    # ========================================================

    def refresh(
        self
    ):

        # Apply lifecycle policy first.

        try:

            cleanup_evidence()

        except Exception as error:

            print(
                "[VIEWER] Cleanup warning:",
                error
            )


        record = latest_evidence()

        self.current_record = record


        if record is None:

            self.current_photo = None

            self.image_label.configure(
                image="",
                text=(
                    "NO UNKNOWN EVIDENCE\n\n"
                    "Sentinel has no temporary "
                    "security image to present."
                )
            )

            self._show_information(
                None
            )

            self._set_actions_enabled(
                False
            )

            return


        evidence_id = record.get(
            "id"
        )


        if evidence_id:

            try:

                mark_presented(
                    evidence_id
                )

            except Exception as error:

                print(
                    "[VIEWER] Presentation warning:",
                    error
                )


            # Reload after state change.

            refreshed = get_evidence(
                evidence_id
            )

            if (
                refreshed.get(
                    "status"
                )
                ==
                "FOUND"
            ):

                record = refreshed.get(
                    "record"
                )

                self.current_record = record


        self._load_image(
            evidence_path(
                record
            )
        )

        self._show_information(
            record
        )

        self._set_actions_enabled(
            True
        )


    # ========================================================
    # KEEP
    # ========================================================

    def keep_current(
        self
    ):

        if not self.current_record:

            return


        evidence_id = self.current_record.get(
            "id"
        )


        messagebox.showinfo(
            "Sentinel Security",
            (
                "Sentinel will now verify "
                "OWNER identity and liveness."
            )
        )


        result = owner_keep_evidence(
            evidence_id
        )


        if result.get(
            "status"
        ) == "KEPT":

            messagebox.showinfo(
                "Sentinel",
                "Evidence preserved."
            )

        else:

            messagebox.showwarning(
                "Sentinel",
                (
                    "Evidence was not preserved.\n\n"
                    f"{result.get('reason', result.get('status'))}"
                )
            )


        self.refresh()


    # ========================================================
    # DELETE
    # ========================================================

    def delete_current(
        self
    ):

        if not self.current_record:

            return


        confirmed = messagebox.askyesno(
            "Delete Evidence",
            (
                "Delete this security evidence?\n\n"
                "OWNER face and active liveness "
                "will still be required."
            )
        )


        if not confirmed:

            return


        evidence_id = self.current_record.get(
            "id"
        )


        result = owner_delete_evidence(
            evidence_id
        )


        if result.get(
            "status"
        ) == "DELETED":

            messagebox.showinfo(
                "Sentinel",
                "Evidence deleted."
            )

        else:

            messagebox.showwarning(
                "Sentinel",
                (
                    "Evidence was not deleted.\n\n"
                    f"{result.get('reason', result.get('status'))}"
                )
            )


        self.refresh()


    # ========================================================
    # ACKNOWLEDGE
    # ========================================================

    def acknowledge_current(
        self
    ):

        if not self.current_record:

            return


        kept = bool(
            self.current_record.get(
                "kept"
            )
        )


        if kept:

            message = (
                "Mark this evidence as reviewed?\n\n"
                "Because it is marked KEEP, "
                "the image will remain stored."
            )

        else:

            message = (
                "Mark this evidence as reviewed?\n\n"
                "Because it is temporary, "
                "acknowledgment may delete it."
            )


        confirmed = messagebox.askyesno(
            "Acknowledge Evidence",
            message
        )


        if not confirmed:

            return


        evidence_id = self.current_record.get(
            "id"
        )


        result = owner_acknowledge_evidence(
            evidence_id
        )


        status = result.get(
            "status"
        )


        if status == "DELETED":

            messagebox.showinfo(
                "Sentinel",
                (
                    "Evidence acknowledged.\n"
                    "Temporary image deleted."
                )
            )

        elif status == "ACKNOWLEDGED":

            messagebox.showinfo(
                "Sentinel",
                (
                    "Evidence acknowledged "
                    "and preserved."
                )
            )

        else:

            messagebox.showwarning(
                "Sentinel",
                (
                    "Evidence was not acknowledged.\n\n"
                    f"{result.get('reason', status)}"
                )
            )


        self.refresh()


# ============================================================
# SELF TEST
# ============================================================

def self_test():

    directory_ok = os.path.isdir(
        EVIDENCE_DIR
    )

    try:

        records = list_evidence()

        lifecycle_ok = isinstance(
            records,
            list
        )

    except Exception:

        lifecycle_ok = False


    try:

        from PIL import ImageTk

        pillow_ok = (
            ImageTk is not None
        )

    except Exception:

        pillow_ok = False


    passed = all(
        [
            directory_ok,
            lifecycle_ok,
            pillow_ok
        ]
    )


    return {

        "status":
            (
                "PASS"
                if passed
                else
                "FAIL"
            ),

        "version":
            VIEWER_VERSION,

        "evidence_directory":
            directory_ok,

        "lifecycle":
            lifecycle_ok,

        "pillow":
            pillow_ok,

        "features": [
            "LATEST_UNKNOWN_IMAGE",
            "INCIDENT_METADATA",
            "MARK_PRESENTED",
            "KEEP",
            "DELETE",
            "ACKNOWLEDGE"
        ],

        "security": {

            "owner_face_for_changes":
                True,

            "owner_liveness_for_changes":
                True,

            "local_image_display":
                True,

            "biometric_upload":
                False,

            "internet_upload":
                False,

            "shell_execution":
                False,

            "payload_execution":
                False
        }
    }


# ============================================================
# RUN VIEWER
# ============================================================

def run():

    root = tk.Tk()

    EvidenceViewer(
        root
    )

    root.mainloop()

    return 0


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    raise SystemExit(
        run()
    )