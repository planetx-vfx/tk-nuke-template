# Copyright (c) 2013 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

import sgtk
import os
import sys
import threading
import nuke

# standard toolkit logger
logger = sgtk.platform.get_logger(__name__)


class NukeTemplateHandler:
    """
    Main application
    """

    def __init__(self):
        """
        Constructor
        """

        self.app = sgtk.platform.current_bundle()

    def check_for_placeholder(self):
        logger.info("Checking for placeholder node.")
        # Checks if script contains the placeholder node
        placeholder_found = False

        nodes = nuke.allNodes()

        for node in nuke.allNodes("ModifyMetaData"):
            if node.name() == "createTemplatePlaceholder":
                placeholder_found = True

        if placeholder_found:
            # If node is found, initiate template generation
            logger.info("Placeholder node found. Initiating template generation...")
            self.generate_template()

        elif len(nodes) == 0:
            self.generate_template()

    def generate_template(self):
        # Script to process nodes
        # nuke.message("Current Context: %s" % self._app.context)
        all_nodes = nuke.allNodes()

        # Creating variable
        write_node = None
        timecode_node = None

        # Handling for when no viewer node exists
        viewer_node = False

        nodes = []
        # Delete unnecessary nodes
        for node in all_nodes:
            if node.Class() == "Group":
                if node["isShotGridWriteNode"]:
                    write_node = node
            if (
                node.name() == "ShotgunWriteNodePlaceholder"
                or node.Class() == "WriteTank"
            ):
                write_node = node
            if node.Class() == "Viewer":
                viewer_node = node
            elif node.Class() == "AddTimeCode":
                timecode_node = node

            if (
                node.Class()
                not in [
                    "Read",
                    "WriteTank",
                    "Group",
                    "ShotgunWriteNodePlaceholder",
                    "createTemplatePlaceholder",
                    "Merge",
                    "TimeOffset",
                    "Viewer",
                    "AddTimeCode",
                ]
                and node.name() != "ShotgunWriteNodePlaceholder"
            ):
                nuke.delete(node)
            else:
                nodes.append(node)

        ### Replacing nodes
        # Calculating ShotGrid template paths
        template_path = self.app.get_template("template_nuke_script")
        current_path = nuke.root().name()
        template_path = template_path.apply_fields(current_path)
        template_path = template_path.replace(os.sep, "/")

        # Pasting template file
        nuke.nodePaste(template_path)
        template = nuke.selectedNodes()

        # Get current location of read node
        read_node = nuke.toNode("Read1")
        read_node_x = 0
        read_node_y = 0
        if read_node is not None:
            read_node_x = read_node["xpos"].value()
            read_node_y = read_node["ypos"].value()
            read_node["label"].setValue("")

        # Get current location of dot
        plate_noop = nuke.toNode("plateNoOp")
        xplate_no_op = plate_noop["xpos"].value()
        yplate_no_op = plate_noop["ypos"].value()

        # Calculate postion adjustment
        x_difference = xplate_no_op - read_node_x
        y_difference = yplate_no_op - read_node_y

        # Replace pasted nodes
        for node in template:
            x_pos = node["xpos"].value()
            y_pos = node["ypos"].value()
            node["xpos"].setValue(x_pos - x_difference)
            node["ypos"].setValue(y_pos - y_difference + 25)

        self._position_additional_read_nodes(nodes, read_node)

        ### Reconnecting nodes
        # Connect read node
        plate_noop.setInput(0, read_node)
        nuke.delete(plate_noop)

        # Reposition write node
        write_no_op = nuke.toNode("writeNoOp")
        x_write_no_op = write_no_op["xpos"].value()
        y_write_no_op = write_no_op["ypos"].value()

        if timecode_node is not None:
            timecode_node.setInput(0, write_no_op)
            timecode_node["xpos"].setValue(x_write_no_op)
            timecode_node["ypos"].setValue(y_write_no_op)

            y_write_no_op += 50
            if write_node is not None:
                write_node.setInput(0, timecode_node)
                write_node["xpos"].setValue(x_write_no_op)
                write_node["ypos"].setValue(y_write_no_op)
        elif write_node is not None:
            write_node.setInput(0, write_no_op)
            write_node["xpos"].setValue(x_write_no_op)
            write_node["ypos"].setValue(y_write_no_op)

        nuke.delete(write_no_op)

        # Reposition viewer node
        if viewer_node:
            viewer_node["xpos"].setValue(x_write_no_op)
            viewer_node["ypos"].setValue(y_write_no_op + 200)

        # Unselect all nodes
        for node in nuke.selectedNodes():
            node["selected"].setValue(False)

    def _position_additional_read_nodes(self, nodes, primary_read_node):
        """Place additional read nodes under a backdrop whose top-left is at elementsNoOp."""

        elements_noop = nuke.toNode("elementsNoOp")
        if not elements_noop:
            return

        if not primary_read_node:
            nuke.delete(elements_noop)
            return

        # Collect reads except the primary one
        additional_read_nodes = [
            n
            for n in nodes
            if n.Class() == "Read" and n.name() != primary_read_node.name()
        ]

        if len(additional_read_nodes) == 0:
            nuke.delete(elements_noop)
            return

        # Anchor (top-left) for the backdrop
        left = int(elements_noop["xpos"].value())
        top = int(elements_noop["ypos"].value())

        # Layout params
        spacing = int(150 * 8 / 1.5)
        inner_margin = 60 * 6
        padding_right = inner_margin
        padding_bottom = inner_margin

        # Place reads starting at an inner offset from the top-left anchor
        start_x = left + inner_margin
        start_y = top + inner_margin

        for idx, read_node in enumerate(
            sorted(additional_read_nodes, key=lambda n: n["xpos"].value())
        ):
            read_node["xpos"].setValue(int(start_x + idx * spacing))
            read_node["ypos"].setValue(int(start_y))
            read_node["label"].setValue("")

        # Compute extents based on newly placed nodes
        max_right = max(
            n["xpos"].value() + n.screenWidth() for n in additional_read_nodes
        )
        max_bottom = max(
            n["ypos"].value() + n.screenHeight() for n in additional_read_nodes
        )

        bd_width = int((max_right + padding_right) - left)
        bd_height = int((max_bottom + padding_bottom) - top)

        # Create backdrop, with its top-left locked to elementsNoOp
        backdrop = nuke.nodes.BackdropNode(name="elementsBackdrop")

        backdrop["xpos"].setValue(left)
        backdrop["ypos"].setValue(top)
        backdrop["bdwidth"].setValue(max(bd_width, 1))
        backdrop["bdheight"].setValue(max(bd_height, 1))
        backdrop["label"].setValue('<img src="Read.png">')
        backdrop["note_font_size"].setValue(100)
        backdrop["tile_color"].setValue(639124735)

        if backdrop["selected"].value():
            backdrop["selected"].setValue(False)

        note_x = left + (inner_margin // 2)
        note_y = top + (inner_margin // 4)

        sticky = nuke.nodes.StickyNote(
            xpos=note_x,
            ypos=note_y,
            label="PLATES",
        )
        sticky["tile_color"].setValue(255)
        sticky["note_font_size"].setValue(100)

        # Clean up the helper NoOp
        nuke.delete(elements_noop)

    def add_callbacks(self):
        # Add callbacks when changing context
        nuke.addOnScriptLoad(self.check_for_placeholder, nodeClass="Root")

    def remove_callbacks(self):
        nuke.removeOnScriptLoad(self.check_for_placeholder, nodeClass="Root")
