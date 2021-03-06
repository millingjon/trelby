# -*- coding: iso-8859-1 -*-

from error import *
import autocompletiondlg
import cfgdlg
import charmapdlg
import commandsdlg
import config
import dialoguechart
import finddlg
import gutil
import headersdlg
import locationsdlg
import math
import misc
import myimport
import mypickle
import namesdlg
import opts
import pml
import scenenav
import reports
import screenplay
import spellcheck
import spellcheckcfgdlg
import spellcheckdlg
import splash
import threading
import titlesdlg
import util
import viewmode
import watermarkdlg

import copy
import datetime
import os
import os.path
import signal
import sys
import time
import wx

from functools import partial

#keycodes
KC_CTRL_A = 1
KC_CTRL_B = 2
KC_CTRL_D = 4
KC_CTRL_E = 5
KC_CTRL_F = 6
KC_CTRL_N = 14
KC_CTRL_P = 16
KC_CTRL_V = 22

VIEWMODE_DRAFT,\
VIEWMODE_LAYOUT,\
VIEWMODE_SIDE_BY_SIDE,\
VIEWMODE_OVERVIEW_SMALL,\
VIEWMODE_OVERVIEW_LARGE,\
= range(5)

# pixels to add to the page width to get the minimum size of window
WIDTH_PADDING = 100

# double-click codes
WORD_NOT_SELECTED = 0
WORD_SELECTED = 1

NAV_TIMER_BUFFER = 500

CURSOR_BLINK_RATE = 500

# How long between saves for crash-recovery?
RECOVERY_TIMER = 90000

def refreshGuiConfig():
    global cfgGui

    cfgGui = config.ConfigGui(cfgGl)

def getCfgGui():
    return cfgGui

# keeps (some) global data
class GlobalData:
    def __init__(self):

        self.confFilename = misc.confPath + "/default.conf"
        self.stateFilename = misc.confPath + "/state"
        self.scDictFilename = misc.confPath + "/spell_checker_dictionary"

        # current screenplay config path
        self.scriptSettingsPath = misc.confPath

        # global spell checker (user) dictionary
        self.scDict = spellcheck.Dict()

        # recently used files list
        self.mru = misc.MRUFiles(5)

        if opts.conf:
            self.confFilename = opts.conf

        v = self.cvars = mypickle.Vars()

        v.addInt("posX", 0, "PositionX", -20, 9999)
        v.addInt("posY", 0, "PositionY", -20, 9999)

        # linux has bigger font by default so it needs a wider window
        defaultW = 750
        if misc.isUnix:
            defaultW = 800

        v.addInt("width", defaultW, "Width", 500, 9999)

        v.addInt("height", 830, "Height", 300, 9999)
        v.addBool("showNavigator", False, "ShowNavigator")
        v.addInt("viewMode", VIEWMODE_LAYOUT, "ViewMode", VIEWMODE_DRAFT,
                 VIEWMODE_OVERVIEW_LARGE)

        v.addList("files", [], "Files",
                  mypickle.StrUnicodeVar("", u"", ""))

        v.makeDicts()
        v.setDefaults(self)

        self.height = min(self.height,
            wx.SystemSettings_GetMetric(wx.SYS_SCREEN_Y) - 50)

        self.vmDraft = viewmode.ViewModeDraft()
        self.vmLayout = viewmode.ViewModeLayout()
        self.vmSideBySide = viewmode.ViewModeSideBySide()
        self.vmOverviewSmall = viewmode.ViewModeOverview(1)
        self.vmOverviewLarge = viewmode.ViewModeOverview(2)

        self.setViewMode(self.viewMode)

        self.makeConfDir()

    def makeConfDir(self):
        makeDir = not util.fileExists(misc.confPath)

        if makeDir:
            try:
                os.mkdir(misc.toPath(misc.confPath), 0755)
            except OSError, (errno, strerror):
                wx.MessageBox("Can't create configuration directory\n"
                              "'%s': %s" % (misc.confPath, strerror),
                              "Error", wx.OK, None)

    # set viewmode, the parameter is one of the VIEWMODE_ defines.
    def setViewMode(self, viewMode):
        self.viewMode = viewMode

        if viewMode == VIEWMODE_DRAFT:
            self.vm = self.vmDraft
        elif viewMode == VIEWMODE_LAYOUT:
            self.vm = self.vmLayout
        elif viewMode == VIEWMODE_SIDE_BY_SIDE:
            self.vm = self.vmSideBySide
        elif viewMode == VIEWMODE_OVERVIEW_SMALL:
            self.vm = self.vmOverviewSmall
        else:
            self.vm = self.vmOverviewLarge

    # load from string 's'. does not throw any exceptions and silently
    # ignores any errors.
    def load(self, s):
        self.cvars.load(self.cvars.makeVals(s), "", self)
        self.mru.items = self.files

    # save to a string and return that.
    def save(self):
        self.files = self.mru.items

        return self.cvars.save("", self)

    # save global spell checker dictionary to disk
    def saveScDict(self):
        util.writeToFile(self.scDictFilename, self.scDict.save(), mainFrame)

class MyPanel(wx.Panel):

    def __init__(self, parent, id):
        wx.Panel.__init__(
            self, parent, id,
            # wxMSW/Windows does not seem to support
            # wx.NO_BORDER, which sucks
            style=wx.WANTS_CHARS | wx.NO_BORDER)

        self.hsizer = wx.BoxSizer(wx.HORIZONTAL)

        self.SetBackgroundColour(cfgGui.workspaceColor)

        self.navsizer = wx.BoxSizer(wx.VERTICAL)
        self.toprow = wx.BoxSizer(wx.HORIZONTAL)
        self.nav = scenenav.MyNavigator(self, -1, getCfgGui)
        self.navclose = misc.MyButton(self, -1, "resources/close.png", getCfgGui)
        self.navclose.SetToolTipString("Close navigator")

        self.toprow.Add(wx.StaticText(self, -1, "Scene navigator"), 1, wx.EXPAND | wx.LEFT | wx.TOP, 5)
        self.toprow.Add(self.navclose)
        self.navsizer.Add(self.toprow, 0,  wx.EXPAND | wx.TOP | wx.BOTTOM | wx.RIGHT, 2)
        self.navsizer.Add(self.nav, 1, wx.EXPAND)

        self.scrollBar = wx.ScrollBar(self, -1, style=wx.SB_VERTICAL)
        self.ctrl = MyCtrl(self, -1)

        self.hsizer.Add(self.ctrl, 1, wx.EXPAND)
        self.hsizer.Add(self.scrollBar, 0, wx.EXPAND)


        self.hsizer.Add(self.navsizer, 0, wx.EXPAND)

        self.navMenu = wx.Menu()
        self.navMenu.Append(ID_NAV_SELECT, "&Select")
        self.navMenu.Append(ID_NAV_DELETE, "&Delete")
        wx.EVT_MENU(self, ID_NAV_SELECT, self.ctrl.OnSelectScene)
        wx.EVT_MENU(self, ID_NAV_DELETE, self.OnContextDelete)

        wx.EVT_COMMAND_SCROLL(self, self.scrollBar.GetId(),
                              self.ctrl.OnScroll)

        wx.EVT_SET_FOCUS(self.scrollBar, self.OnOtherFocus)
        wx.EVT_SET_FOCUS(self.nav, self.OnOtherFocus)
        wx.EVT_LISTBOX(self, self.nav.GetId(), self.OnItemSelected)
        wx.EVT_RIGHT_UP(self.nav, self.OnItemSelected)
        wx.EVT_CONTEXT_MENU(self.nav, self.OnNavContext)
        wx.EVT_BUTTON(self, self.navclose.GetId(), mainFrame.OnToggleShowNavigator)

        # vars to track last line count and line for navigator
        self.lastLineCount = -1
        self.lastLine = -1

        self.SetSizer(self.hsizer)
        self.ShowNavigator(gd.showNavigator)

    # show - bool value indicating if navigator shoulw be shown.
    def ShowNavigator(self, show):
        gd.showNavigator = show
        if show:
            self.hsizer.Show(self.navsizer)
            self.updateNav()
        else:
            self.hsizer.Hide(self.navsizer)
        self.hsizer.Layout()

    # we want only main ctrl widget to get the keyboard focus. When others
    # get it, pass it on the main widget.
    def OnOtherFocus(self, event):
        self.ctrl.SetFocus()

    def OnItemSelected(self, event=None):
        lineno = self.nav.getClickedLineNo()

        if self.ctrl.navTimer.IsRunning():
            self.ctrl.OnNavTimer()

        elif lineno >= len(self.ctrl.sp.lines) or lineno == -1:
            self.updateNav()

        else:
            self.ctrl.sp.clearMark()
            self.ctrl.sp.gotoPos(lineno, 0)
            self.ctrl.makeLineVisible(lineno)
            self.ctrl.updateScreen()

    def OnNavContext(self, event):
        self.ctrl.sp.clearMark()
        self.OnItemSelected()
        self.PopupMenu(self.navMenu)

    def OnContextDelete(self, event):
        self.ctrl.OnSelectScene()
        self.ctrl.OnCut(doUpdate=False, copyToClip=False)
        self.updateNav()

    def updateNav(self):
        # do nothing if navigator is hidden
        if not self.hsizer.IsShown(self.navsizer):
            return
        # update the navigator list
        self.nav.setItems(self.ctrl.sp)
        self.ctrl.lnCountLast = len(self.ctrl.sp.lines)

class MyCtrl(wx.Control):

    def __init__(self, parent, id):
        style = wx.WANTS_CHARS | wx.FULL_REPAINT_ON_RESIZE | wx.NO_BORDER
        wx.Control.__init__(self, parent, id, style=style)

        self.panel = parent

        # recovery controls and callback setup
        self.recoveryFilePath = ""
        self.recoveryTimer = wx.Timer(self)
        wx.EVT_TIMER(self, -1, self.OnRecoveryTimer)

        wx.EVT_SIZE(self, self.OnSize)
        wx.EVT_PAINT(self, self.OnPaint)
        wx.EVT_ERASE_BACKGROUND(self, self.OnEraseBackground)
        wx.EVT_LEFT_DOWN(self, self.OnLeftDown)
        wx.EVT_LEFT_UP(self, self.OnLeftUp)
        wx.EVT_LEFT_DCLICK(self, self.OnLeftDClick)
        wx.EVT_RIGHT_DOWN(self, self.OnRightDown)
        wx.EVT_MOTION(self, self.OnMotion)
        wx.EVT_MOUSEWHEEL(self, self.OnMouseWheel)
        wx.EVT_CHAR(self, self.OnKeyChar)

        self.createEmptySp()

        self.lnCountLast = len(self.sp.lines)

        self.navTimer = wx.Timer(self)
        wx.EVT_TIMER(self, self.navTimer.GetId(), self.OnNavTimer)

        self.setCursorDCs()
        self.updateScreen(redraw=False)
        self.dclick = 0
        self.pos = 0

    def OnNavTimer(self, event=None):
        self.navTimer.Stop()
        self.panel.updateNav()

    def OnChangeType(self, event):
        cs = screenplay.CommandState()

        lt = idToLTMap[event.GetId()]

        self.sp.convertTypeTo(lt, True)
        self.sp.cmdPost(cs)

        if cs.needsVisifying:
            self.makeLineVisible(self.sp.line)

        self.updateScreen()

    def DrawCursor(self, state):
        if misc.doDblBuf:
            dc = wx.ClientDC(self)
        else:
            dc = wx.PaintDC(self)

        if state:
            dc.Blit(self.curx, self.cury, self.curw, self.curh,
                self.cursorDcOn, 0, 0)
        else:
            dc.Blit(self.curx, self.cury, self.curw, self.curh,
                self.cursorDcOff, 0, 0)

    def setCursorDCs(self):
        # create empty DCs which will hold the screen data for when
        # the cursor blink is On or Off. Let the height be a little
        # bigger(10px) to deal with BOLD fonts being longer in some fonts.
        fi = cfgGui.tt2fi(self.sp.cfg.getType(screenplay.SCENE).screen)
        w, h = fi.fx, fi.fy + 10

        self.cursorDcOn = wx.MemoryDC()
        self.cursorDcOn.SelectObject(
            wx.EmptyBitmap(w, h))

        self.cursorDcOff = wx.MemoryDC()
        self.cursorDcOff.SelectObject(
            wx.EmptyBitmap(w, h))

        self.curx, self.cury, self.curw, self.curh = (0, 0, 0, 0)

    def clearVars(self):
        self.mouseSelectActive = False

        # find dialog stored settings
        self.findDlgFindText = ""
        self.findDlgReplaceText = ""
        self.findDlgMatchWholeWord = False
        self.findDlgMatchCase = False
        self.findDlgDirUp = False
        self.findDlgUseExtra = False
        self.findDlgElements = None

    def createEmptySp(self):
        self.clearVars()
        self.sp = screenplay.Screenplay(cfgGl)
        self.sp.titles.addDefaults()
        self.sp.headers.addDefaults()
        self.setFile(None)
        self.refreshCache()

    # update stuff that depends on configuration / view mode etc.
    def refreshCache(self):
        self.chX = util.getTextWidth(" ", pml.COURIER, self.sp.cfg.fontSize)
        self.chY = util.getTextHeight(self.sp.cfg.fontSize)

        self.pageW = gd.vm.getPageWidth(self)

        # conversion factor from mm to pixels
        self.mm2p = self.pageW / self.sp.cfg.paperWidth

        # page width and height on screen, in pixels
        self.pageW = int(self.pageW)
        self.pageH = int(self.mm2p * self.sp.cfg.paperHeight)

        # set minimum width
        if gd.viewMode == VIEWMODE_DRAFT or gd.viewMode == VIEWMODE_LAYOUT:
            w, h = mainFrame.GetSize()
            newMinWidth = self.pageW + WIDTH_PADDING
            if w < newMinWidth:
                mainFrame.SetSize((newMinWidth, -1))
            mainFrame.SetMinSize((newMinWidth, -1))

    def getCfgGui(self):
        return cfgGui

    def loadFile(self, fileName):
        s = util.loadFile(fileName, mainFrame)
        if s is None:
            return

        try:
            (sp, msg) = screenplay.Screenplay.load(s, cfgGl)
        except ScrupulousError, e:
            wx.MessageBox("Can't load file:\n\n%s" % e, "Error",
                          wx.OK, mainFrame)

            return

        if msg:
            misc.showText(mainFrame, msg, "Warning")

        self.clearVars()
        self.sp = sp
        self.setFile(fileName)
        self.refreshCache()

        # saved cursor position might be anywhere, so we can't just
        # display the first page
        self.makeLineVisible(self.sp.line)

    # save screenplay to given filename. returns True on success.
    def saveFile(self, fileName):
        fileName = util.ensureEndsIn(fileName, ".trelby")

        if util.writeToFile(fileName, self.sp.save(), mainFrame):
            self.setFile(fileName)
            self.sp.markChanged(False)
            gd.mru.add(fileName)
            self.initRecovery()

            return True
        else:
            return False

    def importFile(self, fileName):
        if fileName.endswith("fdx"):
            lines = myimport.importFDX(fileName, mainFrame)
        elif fileName.endswith("celtx"):
            lines = myimport.importCeltx(fileName, mainFrame)
        elif fileName.endswith("astx"):
            lines = myimport.importAstx(fileName, mainFrame)
        elif fileName.endswith("fountain"):
            lines = myimport.importFountain(fileName, mainFrame)
        elif fileName.endswith("fadein"):
            lines = myimport.importFadein(fileName, mainFrame)
        else:
            lines = myimport.importTextFile(fileName, mainFrame)

        if not lines:
            return

        self.createEmptySp()

        self.sp.lines = lines
        self.sp.reformatAll()
        self.sp.paginate()
        self.sp.markChanged(True)

    # generate exportable text from given screenplay, or None.
    def getExportText(self, sp):
        inf = []
        inf.append(misc.CheckBoxItem("Include Page Markers"))

        dlg = misc.CheckBoxDlg(mainFrame, "Output Options", inf,
                               "Options", False)

        if dlg.ShowModal() != wx.ID_OK:
            dlg.Destroy()

            return None

        return sp.generateText(inf[0].selected)

    def getExportHtml(self, sp):
        inf = []
        inf.append(misc.CheckBoxItem("Include Notes"))

        dlg = misc.CheckBoxDlg(mainFrame, "Output Options", inf,
                               "Options", False)

        if dlg.ShowModal() != wx.ID_OK:
            dlg.Destroy()

            return None

        return sp.generateHtml(inf[0].selected)

    def setFile(self, fileName):
        self.fileName = fileName
        if fileName:
            self.setDisplayName(os.path.basename(fileName))
        else:
            self.setDisplayName(u"untitled")

        self.setTabText()
        mainFrame.setTitle(self.fileNameDisplay)

        if cfgGl.enableRecovery:
            self.initRecovery()

    def initRecovery(self):
        if self.recoveryFilePath and util.fileExists(self.recoveryFilePath):
            # delete it
            os.remove(self.recoveryFilePath)

        self.recoveryFilePath = util.getRecoveryFilePath(self.fileNameDisplay)
        self.recoveryTimer.Stop()
        self.recoveryTimer.Start(RECOVERY_TIMER)

    def clearRecovery(self):
        self.recoveryTimer.Stop()
        if self.recoveryFilePath and util.fileExists(self.recoveryFilePath):
            os.remove(self.recoveryFilePath)

    def OnRecoveryTimer(self, event):
        if self.sp.isModifiedSinceRecovery():
            util.writeToFile(self.recoveryFilePath, self.sp.save(), mainFrame)
            self.sp.hasChangedSinceRecovery = False

    def setDisplayName(self, name):
        i = 1
        while 1:
            if i == 1:
                tmp = name
            else:
                tmp = name + "-%d" % i

            matched = False

            for c in mainFrame.getCtrls():
                if c == self:
                    continue

                if c.fileNameDisplay == tmp:
                    matched = True

                    break

            if not matched:
                break

            i += 1

        self.fileNameDisplay = tmp

    def setTabText(self):
        mainFrame.setTabText(self.panel, self.fileNameDisplay)

    # texts = gd.vm.getScreen(self, False)[0], or None, in which case it's
    # called in this function.
    def isLineVisible(self, line, texts=None):
        if texts is None:
            texts = gd.vm.getScreen(self, False)[0]

        # paranoia never hurts
        if len(texts) == 0:
            return False

        return (line >= texts[0].line) and (line <= texts[-1].line)

    def makeLineVisible(self, line, direction=config.SCROLL_CENTER):
        texts = gd.vm.getScreen(self, False)[0]

        if self.isLineVisible(line, texts):
            return

        gd.vm.makeLineVisible(self, line, texts, direction)

    def adjustScrollBar(self):
        height = self.GetClientSize().height

        # rough approximation of how many lines fit onto the screen.
        # accuracy is not that important for this, so we don't even care
        # about draft / layout mode differences.
        approx = int(((height / self.mm2p) / self.chY) / 1.3)

        self.panel.scrollBar.SetScrollbar(self.sp.getTopLine(), approx,
            len(self.sp.lines) + approx - 1, approx)

    def clearAutoComp(self):
        if self.sp.clearAutoComp():
            self.Refresh(False)

    # returns true if there are no contents at all and we're not
    # attached to any file
    def isUntouched(self):
        if self.fileName or (len(self.sp.lines) > 1) or \
           (len(self.sp.lines[0].text) > 0):
            return False
        else:
            return True

    def updateScreen(self, redraw=True, setCommon=True, immNavUpdate=False):
        # When line count has changed, or immNavUpdate, immediately
        # udpate navigator, else collate the updates via timer.
        lnCount = len(self.sp.lines)
        if lnCount != self.lnCountLast or immNavUpdate:
            self.panel.updateNav()
        else:
            if self.navTimer.IsRunning():
                self.navTimer.Stop()
                self.navTimer.Start(NAV_TIMER_BUFFER, True)
            else:
                self.navTimer.Start(NAV_TIMER_BUFFER, True)

        self.adjustScrollBar()

        if setCommon:
            self.updateCommon()

        if redraw:
            self.Refresh(False)

    # update GUI elements shared by all screenplays, like statusbar, etc.
    def updateCommon(self):
        cur = cfgGl.getType(self.sp.lines[self.sp.line].lt)

        tabNext, enterNext = self.sp.getTabEnterTypes()

        page = self.sp.line2page(self.sp.line)
        pageCnt = self.sp.line2page(len(self.sp.lines) - 1)

        mainFrame.statusCtrl.SetValues(page, pageCnt, cur.ti.name, tabNext, enterNext)

        canUndo = self.sp.canUndo()
        canRedo = self.sp.canRedo()

        mainFrame.menuBar.Enable(ID_EDIT_UNDO, canUndo)
        mainFrame.menuBar.Enable(ID_EDIT_REDO, canRedo)

        mainFrame.toolBar.EnableTool(ID_EDIT_UNDO, canUndo)
        mainFrame.toolBar.EnableTool(ID_EDIT_REDO, canRedo)

    # apply per-screenplay config
    def applyCfg(self, newCfg):
        self.sp.applyCfg(newCfg)

        self.refreshCache()
        self.makeLineVisible(self.sp.line)
        self.updateScreen()

    # apply global config
    def applyGlobalCfg(self, newCfgGl, writeCfg=True):
        global cfgGl

        oldCfgGl = cfgGl

        cfgGl = copy.deepcopy(newCfgGl)

        # if user has ventured from the old default directory, keep it as
        # the current one, otherwise set the new default as current.
        if misc.scriptDir == oldCfgGl.scriptDir:
            misc.scriptDir = cfgGl.scriptDir

        cfgGl.recalc()
        refreshGuiConfig()
        mainFrame.updateKbdCommands()

        for c in mainFrame.getCtrls():
            c.sp.cfgGl = cfgGl
            c.panel.nav.fullRedraw()
            c.setCursorDCs()
            c.refreshCache()
            c.makeLineVisible(c.sp.line)
            c.adjustScrollBar()
            if cfgGl.enableRecovery:
                c.initRecovery()
            else:
                c.clearRecovery()

        self.updateScreen()

        # in case tab colors have been changed
        mainFrame.tabCtrl.Refresh(False)
        mainFrame.statusCtrl.Refresh(False)
        mainFrame.noFSBtn.Refresh(False)
        mainFrame.toolBar.SetBackgroundColour(cfgGui.tabBarBgColor)

        # update the timer
        mainFrame.resetTimer()

        if writeCfg:
            util.writeToFile(gd.confFilename, cfgGl.save(), mainFrame)

        mainFrame.checkFonts()

    def applyHeaders(self, newHeaders):
        self.sp.headers = newHeaders
        self.sp.markChanged()
        self.OnPaginate()

    # return an exportable, paginated Screenplay object, or None if for
    # some reason that's not possible / wanted. 'action' is the name of
    # the action, e.g. "export" or "print", that'll be done to the
    # screenplay, and is used in dialogue with the user if needed.
    def getExportable(self, action):
        if cfgGl.checkOnExport:
            line = self.sp.findError(0)[0]

            if line != -1:
                if wx.MessageBox(
                    "The screenplay contains errors.\n"
                    "Want to %s it anyway?" % action, "Confirm",
                     wx.YES_NO | wx.NO_DEFAULT, mainFrame) == wx.NO:

                    return None

        sp = self.sp
        if sp.cfg.pdfRemoveNotes:
            sp = copy.deepcopy(self.sp)
            sp.removeElementTypes({screenplay.NOTE: None}, False)

        sp.paginate()

        return sp

    def OnEraseBackground(self, event):
        pass

    def OnSize(self, event):
        if misc.doDblBuf:
            size = self.GetClientSize()

            sb = wx.EmptyBitmap(size.width, size.height)
            old = getattr(self.__class__, "screenBuf", None)

            if (old is None) or (old.GetDepth() != sb.GetDepth()) or \
               (old.GetHeight() != sb.GetHeight()) or \
               (old.GetWidth() != sb.GetWidth()):
                self.__class__.screenBuf = sb

        self.makeLineVisible(self.sp.line)

    # a double-click highlights the current word.
    # a second double-click without moving the mouse highlights the whole line
    # a third double-click without moving the mouse highlights the whole element
    def OnLeftDClick(self, event, mark=False):
        pos = event.GetPosition()
        line, col = gd.vm.pos2linecol(self, 0, pos.y)
        if self.dclick == WORD_NOT_SELECTED or self.pos != pos:
            self.sp.selectWordCmd(line)
            self.dclick = WORD_SELECTED
        elif self.dclick == WORD_SELECTED:
            self.sp.selectElementCmd(line)
            self.dclick = WORD_NOT_SELECTED
        else:
            self.dclick = WORD_NOT_SELECTED
        self.pos = pos
        self.updateScreen()

    def OnLeftDown(self, event, mark=False):
        if not self.mouseSelectActive:
            self.sp.clearMark()
            self.updateScreen()

        pos = event.GetPosition()
        line, col = gd.vm.pos2linecol(self, pos.x, pos.y)

        self.mouseSelectActive = True

        if line is not None:
            self.sp.gotoPos(line, col, mark)
            self.updateScreen(immNavUpdate=True)

    def OnLeftUp(self, event):
        self.mouseSelectActive = False

        # to avoid phantom selections (Windows sends some strange events
        # sometimes), check if anything worthwhile is actually selected.
        cd = self.sp.getSelectedAsCD(False)

        if not cd or ((len(cd.lines) == 1) and (len(cd.lines[0].text) < 2)):
            self.sp.clearMark()

    def OnMotion(self, event):
        if event.LeftIsDown():
            self.OnLeftDown(event, mark=True)

    def OnRightDown(self, event):
        # No popup in the overview modes.
        if gd.viewMode in (VIEWMODE_OVERVIEW_SMALL, VIEWMODE_OVERVIEW_LARGE):
            return

        pos = event.GetPosition()
        line, col = gd.vm.pos2linecol(self, pos.x, pos.y)

        if self.sp.mark:
            m = mainFrame.rightClickMenuWithCut
        else:
            m = mainFrame.rightClickMenu

            if line is not None and (line != self.sp.line):
                self.sp.gotoPos(line, col, False)
                self.updateScreen()

        self.PopupMenu(m)

    def OnMouseWheel(self, event):
        if event.GetWheelRotation() > 0:
            delta = -cfgGl.mouseWheelLines
        else:
            delta = cfgGl.mouseWheelLines

        self.sp.setTopLine(self.sp.getTopLine() + delta)
        self.updateScreen()

    def OnScroll(self, event):
        pos = self.panel.scrollBar.GetThumbPosition()
        self.sp.setTopLine(pos)
        self.sp.clearAutoComp()
        self.updateScreen()

    def OnPaginate(self):
        self.sp.paginate()
        self.makeLineVisible(self.sp.line)
        self.updateScreen()

    def OnAutoCompletionDlg(self):
        dlg = autocompletiondlg.AutoCompletionDlg(mainFrame,
            copy.deepcopy(self.sp.autoCompletion))

        if dlg.ShowModal() == wx.ID_OK:
            self.sp.autoCompletion = dlg.autoCompletion
            self.sp.markChanged()

        dlg.Destroy()

    def OnTitlesDlg(self):
        dlg = titlesdlg.TitlesDlg(mainFrame, copy.deepcopy(self.sp.titles),
                                  self.sp.cfg, cfgGl)

        if dlg.ShowModal() == wx.ID_OK:
            self.sp.titles = dlg.titles
            self.sp.markChanged()

        dlg.Destroy()

    def OnHeadersDlg(self):
        dlg = headersdlg.HeadersDlg(mainFrame,
            copy.deepcopy(self.sp.headers), self.sp.cfg, cfgGl,
                                    self.applyHeaders)

        if dlg.ShowModal() == wx.ID_OK:
            self.applyHeaders(dlg.headers)

        dlg.Destroy()

    def OnLocationsDlg(self):
        dlg = locationsdlg.LocationsDlg(mainFrame, copy.deepcopy(self.sp))

        if dlg.ShowModal() == wx.ID_OK:
            self.sp.locations = dlg.sp.locations
            self.sp.markChanged()

        dlg.Destroy()

    def OnSpellCheckerScriptDictionaryDlg(self):
        dlg = spellcheckcfgdlg.SCDictDlg(mainFrame,
            copy.deepcopy(self.sp.scDict), False)

        if dlg.ShowModal() == wx.ID_OK:
            self.sp.scDict = dlg.scDict
            self.sp.markChanged()

        dlg.Destroy()

    def OnWatermark(self):
        dlg = watermarkdlg.WatermarkDlg(
            mainFrame, self.sp, self.fileNameDisplay.replace(".trelby", ""))
        dlg.ShowModal()
        dlg.Destroy()

    def OnReportDialogueChart(self):
        self.sp.paginate()
        dialoguechart.genDialogueChart(mainFrame, self.sp)

    def OnReportCharacter(self):
        self.sp.paginate()
        reports.genCharacterReport(mainFrame, self.sp)

    def OnReportLocation(self):
        self.sp.paginate()
        reports.genLocationReport(mainFrame, self.sp)

    def OnReportScene(self):
        self.sp.paginate()
        reports.genSceneReport(mainFrame, self.sp)

    def OnReportScreenplay(self):
        self.sp.paginate()
        reports.genScriptReport(mainFrame, self.sp)

    def OnCompareScripts(self):
        if mainFrame.tabCtrl.getPageCount() < 2:
            wx.MessageBox("Can't compare one screenplay.", "Error", wx.OK, mainFrame)

            return

        items = []
        for c in mainFrame.getCtrls():
            items.append(c.fileNameDisplay)

        dlg = misc.ScriptChooserDlg(mainFrame, items)

        sel1 = -1
        sel2 = -1
        if dlg.ShowModal() == wx.ID_OK:
            sel1 = dlg.sel1
            sel2 = dlg.sel2
            force = dlg.forceSameCfg

        dlg.Destroy()

        if sel1 == -1:
            return

        if sel1 == sel2:
            wx.MessageBox("Can't compare a screenplay to itself.", "Error",
                          wx.OK, mainFrame)

            return

        c1 = mainFrame.tabCtrl.getPage(sel1).ctrl
        c2 = mainFrame.tabCtrl.getPage(sel2).ctrl

        sp1 = c1.getExportable("compare")
        sp2 = c2.getExportable("compare")

        if not sp1 or not sp2:
            return

        if force:
            sp2 = copy.deepcopy(sp2)
            sp2.cfg = copy.deepcopy(sp1.cfg)
            sp2.reformatAll()
            sp2.paginate()

        s = sp1.compareScripts(sp2)

        if s:
            gutil.showTempPDF(s, cfgGl, mainFrame)
        else:
            wx.MessageBox("The screenplays are identical.", "Results", wx.OK,
                          mainFrame)

    def canBeClosed(self):
        if self.sp.isModified():
            if wx.MessageBox("Quit without saving?", "Confirm",
                             wx.YES_NO | wx.NO_DEFAULT, mainFrame) == wx.NO:
                return False

        return True

    # page up (dir == -1) or page down (dir == 1) was pressed, handle it.
    # cs = CommandState.
    def pageCmd(self, cs, dir):
        if self.sp.acItems:
            cs.doAutoComp = cs.AC_KEEP
            self.sp.pageScrollAutoComp(dir)

            return

        texts, dpages = gd.vm.getScreen(self, False)

        # if user has scrolled with scrollbar so that cursor isn't seen,
        # just make cursor visible and don't move
        if not self.isLineVisible(self.sp.line, texts):
            gd.vm.makeLineVisible(self, self.sp.line, texts)
            cs.needsVisifying = False

            return

        self.sp.maybeMark(cs.mark)
        gd.vm.pageCmd(self, cs, dir, texts, dpages)

    def OnRevertScript(self):
        if self.fileName:
            if not self.canBeClosed():
                return

            self.loadFile(self.fileName)
            self.updateScreen()

    def OnUndo(self):
        self.sp.cmd("undo")
        self.sp.paginate()
        self.makeLineVisible(self.sp.line)
        self.updateScreen()

    def OnRedo(self):
        self.sp.cmd("redo")
        self.sp.paginate()
        self.makeLineVisible(self.sp.line)
        self.updateScreen()

    def OnUpper(self):
        self.sp.convertToUpper(True)


    # returns True if something was deleted
    def OnCut(self, doUpdate=True, doDelete=True, copyToClip=True):
        marked = self.sp.getMarkedLines()

        if not marked:
            return False

        cd = self.sp.getSelectedAsCD(doDelete)

        if copyToClip:
            mainFrame.clipboard = cd

        if doUpdate:
            self.makeLineVisible(self.sp.line)
            self.updateScreen()

        return doDelete

    def OnCopy(self):
        self.OnCut(doDelete=False)

    def OnCopySystem(self, formatted=False):
        cd = self.sp.getSelectedAsCD(False)

        if not cd:
            return

        tmpSp = screenplay.Screenplay(cfgGl)
        tmpSp.lines = cd.lines

        if formatted:
            # have to call paginate, otherwise generateText will not
            # process all the text
            tmpSp.paginate()
            s = tmpSp.generateText(False)
        else:
            s = util.String()

            for ln in tmpSp.lines:
                txt = ln.text

                if tmpSp.cfg.getType(ln.lt).export.isCaps:
                    txt = util.upper(txt)

                s += txt + config.lb2str(ln.lb)

            s = str(s).replace("\n", os.linesep)

        if wx.TheClipboard.Open():
            wx.TheClipboard.UsePrimarySelection(False)

            wx.TheClipboard.Clear()
            wx.TheClipboard.AddData(wx.TextDataObject(s))
            wx.TheClipboard.Flush()

            wx.TheClipboard.Close()

    def OnPaste(self, clines=None):
        if not clines:
            cd = mainFrame.clipboard

            if not cd:
                return

            clines = cd.lines

        # If there's something selected, remove it.
        if self.sp.mark and cfgGl.overwriteSelectionOnInsert:
            self.OnCut(doUpdate = False, copyToClip = False)
            
        self.sp.paste(clines)

        self.makeLineVisible(self.sp.line)
        self.updateScreen()

    def OnPasteSystemCb(self):
        s = ""

        if wx.TheClipboard.Open():
            wx.TheClipboard.UsePrimarySelection(False)

            df = wx.DataFormat(wx.DF_TEXT)

            if wx.TheClipboard.IsSupported(df):
                data = wx.TextDataObject()
                wx.TheClipboard.GetData(data)
                s = util.cleanInput(data.GetText())

            wx.TheClipboard.Close()

        s = util.fixNL(s)

        if len(s) == 0:
            return

        inLines = s.split("\n")

        # shouldn't be possible, but...
        if len(inLines) == 0:
            return

        lines = []

        for s in inLines:
            if s:
                lines.append(screenplay.Line(screenplay.LB_LAST,
                                             screenplay.ACTION, s))

        self.OnPaste(lines)

    def OnSelectScene(self, e=None):
        self.sp.cmd("selectScene")

        self.makeLineVisible(self.sp.line)
        self.updateScreen()

    def OnSelectElement(self):
        self.sp.cmd("SelectElement")
        self.makelineVisible(self.sp.line)
        self.updateScreen()

    def OnSelectLine(self):
        self.sp.cmd("SelectLine")
        self.makelineVisible(self.sp.line)
        self.updateScreen()

    def OnSelectWord(self):
        self.sp.cmd("SelectWord")
        self.makelineVisible(self.sp.line)
        self.updateScreen()

    def OnSelectAll(self):
        self.sp.cmd("selectAll")

        self.makeLineVisible(self.sp.line)
        self.updateScreen()

    def OnGotoScene(self):
        self.sp.paginate()
        self.clearAutoComp()

        scenes = self.sp.getSceneLocations()

        def validateFunc(s):
            if s in [x[0] for x in scenes]:
                return ""
            else:
                return "Invalid Scene Number"

        dlg = misc.TextInputDlg(mainFrame, "Enter Scene Number (%s - %s):" %
            (scenes[0][0], scenes[-1][0]), "Go to Scene", validateFunc)

        if dlg.ShowModal() == wx.ID_OK:
            for it in scenes:
                if it[0] == dlg.input:
                    self.sp.line = it[1]
                    self.sp.column = 0

                    break

        # we need to refresh the screen in all cases because pagination
        # might have changed
        self.makeLineVisible(self.sp.line)
        self.updateScreen()

    def OnGotoPage(self):
        self.sp.paginate()
        self.clearAutoComp()

        pages = self.sp.getPageNumbers()

        def validateFunc(s):
            if s in pages:
                return ""
            else:
                return "Invalid Page Number"

        dlg = misc.TextInputDlg(mainFrame, "Enter Page Number (%s - %s):" %
            (pages[0], pages[-1]), "Go to Page", validateFunc)

        if dlg.ShowModal() == wx.ID_OK:
            page = int(dlg.input)
            self.sp.line = self.sp.page2lines(page)[0]
            self.sp.column = 0

        # we need to refresh the screen in all cases because pagination
        # might have changed
        self.makeLineVisible(self.sp.line)
        self.updateScreen()

    def OnInsertNbsp(self):
        self.OnKeyChar(util.MyKeyEvent(160))

    def OnFindNextError(self):
        self.clearAutoComp()

        line, msg = self.sp.findError(self.sp.line)

        if line != -1:
            self.sp.line = line
            self.sp.column = 0

            self.makeLineVisible(self.sp.line)
            self.updateScreen()

        else:
            msg = "No Errors Found"

        wx.MessageBox(msg, "Results", wx.OK, mainFrame)

    def OnFind(self):
        self.sp.clearMark()
        self.clearAutoComp()
        self.updateScreen()

        dlg = finddlg.FindDlg(mainFrame, self)
        dlg.ShowModal()
        dlg.saveState()
        dlg.Destroy()

        self.sp.clearMark()
        self.makeLineVisible(self.sp.line)
        self.updateScreen()

    def OnSpellCheckerDlg(self):
        self.sp.clearMark()
        self.clearAutoComp()
        self.sp.clearMark()
        self.mouseSelectActive = False
        self.updateScreen()
        
        wx.BeginBusyCursor()

        if not spellcheck.loadDict(mainFrame):
            wx.EndBusyCursor()

            return

        sc = spellcheck.SpellChecker(self.sp, gd.scDict)
        found = sc.findNext()

        wx.EndBusyCursor()

        if not found:
            wx.MessageBox("No spelling error found.", "Results",
                          wx.OK, mainFrame)

            return

        dlg = spellcheckdlg.SpellCheckDlg(mainFrame, self, sc, gd.scDict)
        dlg.ShowModal()

        if dlg.changedGlobalDict:
            gd.saveScDict()

        dlg.Destroy()

        self.sp.clearMark()
        self.makeLineVisible(self.sp.line)
        self.updateScreen()

    def OnDeleteElements(self):
        # even though Screenplay.removeElementTypes does this as well, do
        # it here so that screen is cleared from the auto-comp box before
        # we open the dialog
        self.clearAutoComp()

        types = []
        for t in config.getTIs():
            types.append(misc.CheckBoxItem(t.name, False, t.lt))

        dlg = misc.CheckBoxDlg(mainFrame, "Delete elements", types,
                               "Element types to delete", True)

        ok = False
        if dlg.ShowModal() == wx.ID_OK:
            ok = True

            tdict = misc.CheckBoxItem.getClientData(types)

        dlg.Destroy()

        if not ok or (len(tdict) == 0):
            return

        self.sp.removeElementTypes(tdict, True)
        self.sp.paginate()
        self.makeLineVisible(self.sp.line)
        self.updateScreen()

    def OnSave(self):
        if self.fileName:
            self.saveFile(self.fileName)
        else:
            self.OnSaveScriptAs()

    def OnAutoSave(self, count=None):
        if self.fileName:
            self.saveFile(self.fileName)
        else:
            self.OnSaveUntitledScript(count)

    def OnSaveUntitledScript(self, count):
        # check if we can write this file to default screenplay directory.
        if os.access(misc.scriptDir, os.W_OK):
            if misc.isWindows:
                div = "\\"
            else:
                div = "/"
        # don't use colons for filename below as may cause issues with OS X.
            self.saveFile(misc.scriptDir + div + "untitled-" +
                time.strftime("%Y-%m-%d-%H.%M.%S") + "-tab-" +
                str(count) + ".trelby")

    def OnSaveScriptAs(self):
        if self.fileName:
            dDir = os.path.dirname(self.fileName)
            dFile = os.path.basename(self.fileName)
        else:
            dDir = misc.scriptDir
            dFile = u""

        dlg = wx.FileDialog(mainFrame, "Save Screenplay As",
            defaultDir=dDir,
            defaultFile=dFile,
            wildcard="Trelby files (*.trelby)|*.trelby|All files|*",
            style=wx.SAVE | wx.OVERWRITE_PROMPT)
        if dlg.ShowModal() == wx.ID_OK:
            self.saveFile(dlg.GetPath())

        dlg.Destroy()

    def OnExportScript(self):
        sp = self.getExportable("export")
        if not sp:
            return

        dlg = wx.FileDialog(mainFrame, "Export Screenplay As",
            misc.scriptDir,
            wildcard="PDF|*.pdf|"
                       "RTF|*.rtf|"
                       "Final Draft XML|*.fdx|"
                       "HTML|*.html|"
                       "Fountain|*.fountain|"
                       "Formatted text|*.txt",
            style=wx.SAVE | wx.OVERWRITE_PROMPT)

        if dlg.ShowModal() == wx.ID_OK:
            misc.scriptDir = dlg.GetDirectory()

            choice = dlg.GetFilterIndex()
            if choice == 0:
                data = sp.generatePDF(True)
                suffix = ".pdf"
            elif choice == 1:
                data = sp.generateRTF()
                suffix = ".rtf"
            elif choice == 2:
                data = sp.generateFDX()
                suffix = ".fdx"
            elif choice == 3:
                data = self.getExportHtml(sp)
                suffix = ".html"
            elif choice == 4:
                data = sp.generateFountain()
                suffix = ".fountain"
            else:
                data = self.getExportText(sp)
                suffix = ".txt"

            fileName = util.ensureEndsIn(dlg.GetPath(), suffix)

            if data:
                util.writeToFile(fileName, data, mainFrame)

        dlg.Destroy()

    def OnPrint(self):
        sp = self.getExportable("print")
        if not sp:
            return

        s = sp.generatePDF(False)
        gutil.showTempPDF(s, cfgGl, mainFrame)

    def OnSettings(self):
        dlg = cfgdlg.CfgDlg(mainFrame, copy.deepcopy(cfgGl),
                            self.applyGlobalCfg, True)

        if dlg.ShowModal() == wx.ID_OK:
            self.applyGlobalCfg(dlg.cfg)

        dlg.Destroy()

    def OnScriptSettings(self):
        dlg = cfgdlg.CfgDlg(mainFrame, copy.deepcopy(self.sp.cfg),
                            self.applyCfg, False)

        if dlg.ShowModal() == wx.ID_OK:
            self.applyCfg(dlg.cfg)

        dlg.Destroy()

    def cmdAbort(self, cs):
        self.sp.abortCmd(cs)

    def cmdChangeToUpper(self, cs):
        self.sp.convertToUpper(True)

    def cmdChangeToAction(self, cs):
        self.sp.toActionCmd(cs)

    def cmdChangeToCharacter(self, cs):
        self.sp.toCharacterCmd(cs)

    def cmdChangeToDialogue(self, cs):
        self.sp.toDialogueCmd(cs)

    def cmdChangeToNote(self, cs):
        self.sp.toNoteCmd(cs)

    def cmdChangeToParenthetical(self, cs):
        self.sp.toParenCmd(cs)

    def cmdChangeToScene(self, cs):
        self.sp.toSceneCmd(cs)

    def cmdChangeToShot(self, cs):
        self.sp.toShotCmd(cs)

    def cmdChangeToActBreak(self, cs):
        self.sp.toActBreakCmd(cs)

    def cmdChangeToTitle(self, cs):
        self.sp.toTitleCmd(cs)

    def cmdChangeToTransition(self, cs):
        self.sp.toTransitionCmd(cs)

    def cmdDelete(self, cs):
        if not self.sp.mark:
            self.sp.deleteForwardCmd(cs)
        else:
            self.OnCut(doUpdate=False, copyToClip=False)

    def cmdDeleteBackward(self, cs):
        if not self.sp.mark:
            self.sp.deleteBackwardCmd(cs)
            self.sp.backspacePressed = True
        else:
            self.OnCut(doUpdate=False, copyToClip=False)

    def cmdForcedLineBreak(self, cs):
        self.sp.insertForcedLineBreakCmd(cs)

    def cmdMoveDown(self, cs):
        self.sp.moveDownCmd(cs)

    def cmdMoveEndOfLine(self, cs):
        self.sp.moveLineEndCmd(cs)

    def cmdMoveEndOfScript(self, cs):
        self.sp.moveEndCmd(cs)

    def cmdMoveLeft(self, cs):
        self.sp.moveLeftCmd(cs)

    def cmdMoveNextWord(self, cs):
        self.sp.moveNextWordCmd(cs)

    def cmdMovePageDown(self, cs):
        self.pageCmd(cs, 1)

    def cmdMovePageUp(self, cs):
        self.pageCmd(cs, -1)

    def cmdMovePrevWord(self, cs):
        self.sp.movePrevWordCmd(cs)

    def cmdMoveRight(self, cs):
        self.sp.moveRightCmd(cs)

    def cmdMoveSceneDown(self, cs):
        self.sp.moveSceneDownCmd(cs)

    def cmdMoveSceneUp(self, cs):
        self.sp.moveSceneUpCmd(cs)

    def cmdMoveStartOfLine(self, cs):
        self.sp.moveLineStartCmd(cs)

    def cmdMoveStartOfScript(self, cs):
        self.sp.moveStartCmd(cs)

    def cmdMoveUp(self, cs):
        self.sp.moveUpCmd(cs)

    def cmdNewElement(self, cs):
        self.sp.splitElementCmd(cs)

    def cmdSetMark(self, cs):
        self.sp.setMarkCmd(cs)

    def cmdTab(self, cs):
        self.sp.tabCmd(cs)

    def cmdTabPrev(self, cs):
        self.sp.toPrevTypeTabCmd(cs)

    def cmdSpeedTest(self, cs):
        import undo
        self.speedTestUndo = []

        def testUndoFullCopy():
            u = undo.FullCopy(self.sp)
            u.setAfter(self.sp)
            self.speedTestUndo.append(u)

        def testReformatAll():
            self.sp.reformatAll()

        def testPaginate():
            self.sp.paginate()

        def testUpdateScreen():
            self.updateScreen()
            self.Update()

        def testAddRemoveChar():
            self.OnKeyChar(util.MyKeyEvent(ord("a")))
            self.OnKeyChar(util.MyKeyEvent(wx.WXK_BACK))

        def testDeepcopy():
            copy.deepcopy(self.sp)

        # contains (name, func) tuples
        tests = []

        for name, var in locals().iteritems():
            if callable(var):
                tests.append((name, var))

        tests.sort()
        count = 100

        print "-" * 20

        for name, func in tests:
            t = time.time()

            for i in xrange(count):
                func()

            t = time.time() - t

            print "%.5f Seconds Per %s" % (t / count, name)

        print "-" * 20

        # it's annoying having the program ask if you want to save after
        # running these tests, so pretend the screenplay hasn't changed
        self.sp.markChanged(False)

    def cmdTest(self, cs):
        pass

    def OnKeyChar(self, ev):
        kc = ev.GetKeyCode()

        #print "kc: %d, ctrl/alt/shift: %d, %d, %d" %\
        #      (kc, ev.ControlDown(), ev.AltDown(), ev.ShiftDown())

        cs = screenplay.CommandState()
        cs.mark = bool(ev.ShiftDown())
        scrollDirection = config.SCROLL_CENTER

        if not ev.ControlDown() and not ev.AltDown() and \
               util.isValidInputChar(kc):
            # WX2.6-FIXME: we should probably use GetUnicodeKey() (dunno
            # how to get around the isValidInputChar test in the preceding
            # line, need to test what GetUnicodeKey() returns on
            # non-input-character events)

            addChar = True

            # If text is selected, either remove it, or clear selection.
            if self.sp.mark and cfgGl.overwriteSelectionOnInsert:
                if not self.OnCut(doUpdate=False, copyToClip=False):
                    self.sp.clearMark()
                    addChar = False

            if addChar:
                cs.char = chr(kc)

                if opts.isTest and (cs.char == "?"):
                    self.loadFile(u"sample.trelby")
                elif opts.isTest and (cs.char == "?"):
                    self.cmdTest(cs)
                elif opts.isTest and (cs.char == "?"):
                    self.cmdSpeedTest(cs)
                else:
                    self.sp.addCharCmd(cs)

        else:
            cmd = mainFrame.kbdCommands.get(util.Key(kc,
                ev.ControlDown(), ev.AltDown(), ev.ShiftDown()).toInt())

            if cmd:
                scrollDirection = cmd.scrollDirection
                if cmd.isMenu:
                    getattr(mainFrame, "On" + cmd.name)()
                    return
                else:
                    getattr(self, "cmd" + cmd.name)(cs)
            else:
                ev.Skip()
                return

        self.sp.cmdPost(cs)

        if cfgGl.paginateInterval > 0:
            now = time.time()

            if (now - self.sp.lastPaginated) >= cfgGl.paginateInterval:
                self.sp.paginate()

                cs.needsVisifying = True

        if cs.needsVisifying:
            self.makeLineVisible(self.sp.line, scrollDirection)

        self.updateScreen()

    def OnPaint(self, event):
        #ldkjfldsj = util.TimerDev("paint")

        ls = self.sp.lines
        mainFrame.cursorTimer.Stop()

        if misc.doDblBuf:
            dc = wx.BufferedPaintDC(self, self.screenBuf)
        else:
            dc = wx.PaintDC(self)

        size = self.GetClientSize()
        marked = self.sp.getMarkedLines()
        lineh = gd.vm.getLineHeight(self)
        posX = -1
        cursorY = -1
        cursorFound = False

        # auto-comp FontInfo
        acFi = None

        # key = font, value = ([text, ...], [(x, y), ...], [wx.Colour, ...])
        texts = {}

        # lists of underline-lines to draw, one for normal text and one
        # for header texts. list objects are (x, y, width) tuples.
        ulines = []
        ulinesHdr = []

        strings, dpages = gd.vm.getScreen(self, True, True)

        dc.SetBrush(cfgGui.workspaceBrush)
        dc.SetPen(cfgGui.workspacePen)
        dc.DrawRectangle(0, 0, size.width, size.height)

        dc.SetPen(cfgGui.tabBorderPen)
        dc.DrawLine(0, 0, 0, size.height)
        dc.DrawLine(size.width - 1, 0, size.width - 1, size.height)

        if not dpages:
            # draft mode; draw an infinite page
            lx = util.clamp((size.width - self.pageW) // 2, 0)
            rx = lx + self.pageW

            dc.SetBrush(cfgGui.textBgBrush)
            dc.SetPen(cfgGui.textBgPen)
            dc.DrawRectangle(lx, 5, self.pageW, size.height - 5)

            dc.SetPen(cfgGui.pageBorderPen)
            dc.DrawLine(lx, 5, lx, size.height)
            dc.DrawLine(rx, 5, rx, size.height)

        else:
            dc.SetBrush(cfgGui.textBgBrush)
            dc.SetPen(cfgGui.pageBorderPen)
            for dp in dpages:
                dc.DrawRectangle(dp.x1, dp.y1, dp.x2 - dp.x1 + 1,
                                 dp.y2 - dp.y1 + 1)

            dc.SetPen(cfgGui.pageShadowPen)
            for dp in dpages:
                # + 2 because DrawLine doesn't draw to end point but stops
                # one pixel short...
                dc.DrawLine(dp.x1 + 2, dp.y2 + 2, dp.x2 + 2, dp.y2 + 2)
                dc.DrawLine(dp.x2 + 2, dp.y1 + 2, dp.x2 + 2, dp.y2 + 3)

        for t in strings:
            i = t.line
            y = t.y
            fi = t.fi
            fx = fi.fx

            if i != -1:
                l = ls[i]

                if l.lt == screenplay.NOTE:
                    dc.SetPen(cfgGui.notePen)
                    dc.SetBrush(cfgGui.noteBrush)

                    nx = t.x - 5
                    nw = self.sp.cfg.getType(l.lt).width * fx + 10

                    dc.DrawRectangle(nx, y, nw, lineh)

                    dc.SetPen(cfgGui.textPen)
                    util.drawLine(dc, nx - 1, y, 0, lineh)
                    util.drawLine(dc, nx + nw, y, 0, lineh)

                    if self.sp.isFirstLineOfElem(i):
                        util.drawLine(dc, nx - 1, y - 1, nw + 2, 0)

                    if self.sp.isLastLineOfElem(i):
                        util.drawLine(dc, nx - 1, y + lineh,
                                      nw + 2, 0)

                if marked and self.sp.isLineMarked(i, marked):
                    c1, c2 = self.sp.getMarkedColumns(i, marked)

                    dc.SetPen(cfgGui.selectedPen)
                    dc.SetBrush(cfgGui.selectedBrush)

                    width_in_chars = c2 - c1
                    if width_in_chars == 0:
                        # the line is empty or we are at the end of a line;
                        # draw a one-character rectangle to show that it is
                        # selected
                        width_in_chars = 1
                        
                    dc.DrawRectangle(t.x + c1 * math.ceil(fx), y, width_in_chars * fx,
                        lineh)

                if mainFrame.showFormatting:
                    dc.SetPen(cfgGui.bluePen)
                    util.drawLine(dc, t.x, y, 0, lineh)

                    extraIndent = 1 if self.sp.needsExtraParenIndent(i) else 0

                    util.drawLine(dc,
                        t.x + (self.sp.cfg.getType(l.lt).width - extraIndent) * fx,
                        y, 0, lineh)

                    dc.SetTextForeground(cfgGui.redColor)
                    dc.SetFont(cfgGui.fonts[pml.NORMAL].font)
                    dc.DrawText(config.lb2char(l.lb), t.x - 10, y)

                if not dpages:
                    if cfgGl.pbi == config.PBI_REAL_AND_UNADJ:
                        if self.sp.line2pageNoAdjust(i) != \
                               self.sp.line2pageNoAdjust(i + 1):
                            dc.SetPen(cfgGui.pagebreakNoAdjustPen)
                            util.drawLine(dc, 0, y + lineh - 1,
                                size.width, 0)

                    if cfgGl.pbi in (config.PBI_REAL,
                                   config.PBI_REAL_AND_UNADJ):
                        thisPage = self.sp.line2page(i)

                        if thisPage != self.sp.line2page(i + 1):
                            dc.SetPen(cfgGui.pagebreakPen)
                            util.drawLine(dc, 0, y + lineh - 1,
                                size.width, 0)

                if i == self.sp.line:
                    posX = t.x
                    cursorY = y
                    acFi = fi
                    cfont = fi.font
                    cx, cy, cw, ch = t.x + self.sp.column * fx, y, fx, fi.fy
                    if self.sp.column > len(t.text) - 1:
                        cchar = ""
                    else:
                        cchar = t.text[self.sp.column]

                    if cfgGl.useCustomElemColors:
                        ccol = cfgGui.lt2textColor(ls[t.line].lt)
                    else:
                        ccol = cfgGui.textColor
                    cursorFound = True

            if len(t.text) != 0:
                tl = texts.get(fi.font)
                if tl is None:
                    tl = ([], [], [])
                    texts[fi.font] = tl

                tl[0].append(t.text)
                tl[1].append((t.x, y))
                if t.line != -1:
                    if cfgGl.useCustomElemColors:
                        tl[2].append(cfgGui.lt2textColor(ls[t.line].lt))
                    else:
                        tl[2].append(cfgGui.textColor)
                else:
                    tl[2].append(cfgGui.textHdrColor)

                if t.isUnderlined:
                    if t.line != -1:
                        uli = ulines
                    else:
                        uli = ulinesHdr

                    uli.append((t.x, y + lineh - 1,
                               len(t.text) * fx - 1))

        if ulines:
            dc.SetPen(cfgGui.textPen)

            for ul in ulines:
                util.drawLine(dc, ul[0], ul[1], ul[2], 0)

        if ulinesHdr:
            dc.SetPen(cfgGui.textHdrPen)

            for ul in ulinesHdr:
                util.drawLine(dc, ul[0], ul[1], ul[2], 0)

        for tl in texts.iteritems():
            gd.vm.drawTexts(self, dc, tl)

        if self.sp.acItems and (cursorY > 0):
            self.drawAutoComp(dc, posX, cursorY, acFi)

        if cursorFound and gd.viewMode not in (
                VIEWMODE_OVERVIEW_SMALL, VIEWMODE_OVERVIEW_LARGE):
            # copy after state (as is)
            self.cursorDcOff.Blit(0, 0, cw, ch, dc, cx, cy)

            if cfgGl.useBlockCursor:
                # draw the cursor ..
                dc.SetPen(cfgGui.cursorPen)
                dc.SetBrush(cfgGui.cursorBrush)
                dc.DrawRectangle(cx, cy, cw, ch)
                # .. and the character
                dc.SetPen(wx.Pen(ccol))
                dc.SetTextForeground(ccol)
                dc.SetFont(cfont)
                dc.DrawText(cchar, cx, cy)

            else:
                # draw only the cursor.
                height = 1 + (ch // 8)
                dc.SetPen(wx.Pen(ccol))
                dc.SetBrush(wx.Brush(ccol))
                dc.DrawRectangle(cx, cy + (ch - height), cw, height)

            # save ON state.
            self.cursorDcOn.Blit(0, 0, cw, ch, dc, cx, cy)

            self.curx, self.cury, self.curw, self.curh = cx, cy, cw, ch

            if cfgGl.blinkCursor:
                # reset cursor timer, so we don't blink when typing.
                mainFrame.cursorTimer.Start(CURSOR_BLINK_RATE // 2)

    def drawAutoComp(self, dc, posX, cursorY, fi):
        ac = self.sp.acItems
        asel = self.sp.acSel

        offset = 5
        selBleed = 2

        # scroll bar width
        sbw = 10

        size = self.GetClientSize()

        dc.SetFont(fi.font)

        show = min(self.sp.acMax, len(ac))
        doSbw = show < len(ac)

        startPos = (asel // show) * show
        endPos = min(startPos + show, len(ac))
        if endPos == len(ac):
            startPos = max(0, endPos - show)

        w = 0
        for i in range(len(ac)):
            tw = dc.GetTextExtent(ac[i])[0]
            w = max(w, tw)

        w += offset * 2
        h = show * fi.fy + offset * 2

        itemW = w - offset * 2 + selBleed * 2
        if doSbw:
            w += sbw + offset * 2
            sbh = h - offset * 2 + selBleed * 2

        posY = cursorY + fi.fy + 5

        # if the box doesn't fit on the screen in the normal position, put
        # it above the current line. if it doesn't fit there either,
        # that's just too bad, we don't support window sizes that small.
        if (posY + h) > size.height:
            posY = cursorY - h - 1

        dc.SetPen(cfgGui.autoCompPen)
        dc.SetBrush(cfgGui.autoCompBrush)
        dc.DrawRectangle(posX, posY, w, h)

        dc.SetTextForeground(cfgGui.autoCompFgColor)

        for i in range(startPos, endPos):
            if i == asel:
                dc.SetPen(cfgGui.autoCompRevPen)
                dc.SetBrush(cfgGui.autoCompRevBrush)
                dc.SetTextForeground(cfgGui.autoCompBgColor)
                dc.DrawRectangle(posX + offset - selBleed,
                    posY + offset + (i - startPos) * fi.fy - selBleed,
                    itemW,
                    fi.fy + selBleed * 2)
                dc.SetTextForeground(cfgGui.autoCompBgColor)
                dc.SetPen(cfgGui.autoCompPen)
                dc.SetBrush(cfgGui.autoCompBrush)

            dc.DrawText(ac[i], posX + offset, posY + offset +
                        (i - startPos) * fi.fy)

            if i == asel:
                dc.SetTextForeground(cfgGui.autoCompFgColor)

        if doSbw:
            dc.SetPen(cfgGui.autoCompPen)
            dc.SetBrush(cfgGui.autoCompRevBrush)
            util.drawLine(dc, posX + w - offset * 2 - sbw,
                posY, 0, h)
            dc.DrawRectangle(posX + w - offset - sbw,
                posY + offset - selBleed + int((float(startPos) /
                     len(ac)) * sbh),
                sbw, int((float(show) / len(ac)) * sbh))

class MyFrame(wx.Frame):

    def __init__(self, parent, id, title):
        wx.Frame.__init__(self, parent, id, title, name="Scrupulous")

        if misc.isUnix:
            # automatically reaps zombies
            signal.signal(signal.SIGCHLD, signal.SIG_IGN)

        self.clipboard = None
        self.showFormatting = False

        self.SetSizeHints(gd.cvars.getMin("width"),
                          gd.cvars.getMin("height"))

        self.MoveXY(gd.posX, gd.posY)
        self.SetSize(wx.Size(gd.width, gd.height))

        util.removeTempFiles(misc.tmpPrefix)

        self.mySetIcons()
        self.allocIds()

        fileMenu = wx.Menu()
        fileMenu.Append(ID_FILE_NEW, "&New\tCTRL-N")
        fileMenu.Append(ID_FILE_OPEN, "&Open...\tCTRL-O")
        fileMenu.Append(ID_FILE_SAVE, "&Save\tCTRL-S")
        fileMenu.Append(ID_FILE_SAVE_AS, "Save &As...")
        fileMenu.Append(ID_FILE_CLOSE, "&Close\tCTRL-W")
        fileMenu.Append(ID_FILE_REVERT, "&Revert")
        fileMenu.AppendSeparator()
        fileMenu.Append(ID_FILE_IMPORT, "&Import...")
        fileMenu.Append(ID_FILE_EXPORT, "&Export...")
        fileMenu.AppendSeparator()
        fileMenu.Append(ID_FILE_PRINT, "&Print as PDF\tCTRL-P")
        fileMenu.AppendSeparator()

        tmp = wx.Menu()

        tmp.Append(ID_SETTINGS_CHANGE, "&Change...")
        tmp.AppendSeparator()
        tmp.Append(ID_SETTINGS_LOAD, "Load...")
        tmp.Append(ID_SETTINGS_SAVE_AS, "Save as...")
        tmp.AppendSeparator()
        tmp.Append(ID_SETTINGS_SC_DICT, "&Spell Checker Dictionary...")
        settingsMenu = tmp

        fileMenu.AppendMenu(ID_FILE_SETTINGS, "Se&ttings", tmp)

        fileMenu.AppendSeparator()
        # "most recently used" list comes in here
        fileMenu.AppendSeparator()
        fileMenu.Append(ID_FILE_EXIT, "E&xit\tCTRL-Q")

        editMenu = wx.Menu()
        editMenu.Append(ID_EDIT_UNDO, "&Undo\tCTRL-Z")
        editMenu.Append(ID_EDIT_REDO, "&Redo\tCTRL-Y")
        editMenu.AppendSeparator()
        editMenu.Append(ID_EDIT_CUT, "Cu&t\tCTRL-X")
        editMenu.Append(ID_EDIT_COPY, "&Copy\tCTRL-C")
        editMenu.Append(ID_EDIT_PASTE, "&Paste\tCTRL-V")
        editMenu.AppendSeparator()
        editMenu.Append(ID_EDIT_UPPER, "Make Uppercase\tCTRL-K")
        editMenu.AppendSeparator()

        tmp = wx.Menu()
        tmp.Append(ID_EDIT_COPY_TO_CB, "&Unformatted")
        tmp.Append(ID_EDIT_COPY_TO_CB_FMT, "&Formatted")

        editMenu.AppendMenu(ID_EDIT_COPY_SYSTEM, "C&opy (system)", tmp)
        editMenu.Append(ID_EDIT_PASTE_FROM_CB, "P&aste (system)")
        editMenu.AppendSeparator()
        editMenu.Append(ID_EDIT_SELECT_SCENE, "&Select Scene")
        editMenu.Append(ID_EDIT_SELECT_ALL, "Select A&ll\tCTRL-A")
        editMenu.Append(ID_EDIT_GO_TO_PAGE, "&Go to Page...\tCTRL-G")
        editMenu.Append(ID_EDIT_GO_TO_SCENE, "Go to Sc&ene...\tALT-G")
        editMenu.AppendSeparator()
        editMenu.Append(ID_EDIT_INSERT_NBSP, "Insert Non-breaking Space")
        editMenu.AppendSeparator()
        editMenu.Append(ID_EDIT_FIND, "&Find && Replace...\tCTRL-F")
        editMenu.AppendSeparator()
        editMenu.Append(ID_EDIT_DELETE_ELEMENTS, "&Delete Elements...")

        viewMenu = wx.Menu()
        viewMenu.AppendRadioItem(ID_VIEW_STYLE_DRAFT, "&Draft")
        viewMenu.AppendRadioItem(ID_VIEW_STYLE_LAYOUT, "&Layout")
        viewMenu.AppendRadioItem(ID_VIEW_STYLE_SIDE_BY_SIDE, "&Side by Side")
        viewMenu.AppendRadioItem(ID_VIEW_STYLE_OVERVIEW_SMALL,
                                 "&Overview - Small")
        viewMenu.AppendRadioItem(ID_VIEW_STYLE_OVERVIEW_LARGE,
                                 "O&verview - Large")

        if gd.viewMode == VIEWMODE_DRAFT:
            viewMenu.Check(ID_VIEW_STYLE_DRAFT, True)
        elif gd.viewMode == VIEWMODE_LAYOUT:
            viewMenu.Check(ID_VIEW_STYLE_LAYOUT, True)
        elif gd.viewMode == VIEWMODE_SIDE_BY_SIDE:
            viewMenu.Check(ID_VIEW_STYLE_SIDE_BY_SIDE, True)
        elif gd.viewMode == VIEWMODE_OVERVIEW_SMALL:
            viewMenu.Check(ID_VIEW_STYLE_OVERVIEW_SMALL, True)
        else:
            viewMenu.Check(ID_VIEW_STYLE_OVERVIEW_LARGE, True)

        viewMenu.AppendSeparator()
        viewMenu.AppendCheckItem(ID_VIEW_SHOW_FORMATTING, "&Show Formatting\tCTRL-ALT-F")
        viewMenu.AppendCheckItem(ID_VIEW_SHOW_NAVIGATOR, "Show Scene &Navigator\tF9")
        if gd.showNavigator:
            viewMenu.Check(ID_VIEW_SHOW_NAVIGATOR, True)
        viewMenu.Append(ID_VIEW_FULL_SCREEN, "&Fullscreen\tF11")

        screenplayMenu = wx.Menu()
        screenplayMenu.Append(ID_SCREENPLAY_FIND_ERROR, "&Find Next Error")
        screenplayMenu.Append(ID_SCREENPLAY_PAGINATE, "&Paginate")
        screenplayMenu.AppendSeparator()
        screenplayMenu.Append(ID_SCREENPLAY_AUTO_COMPLETION, "&Auto-completion...")
        screenplayMenu.Append(ID_SCREENPLAY_HEADERS, "&Headers...")
        screenplayMenu.Append(ID_SCREENPLAY_LOCATIONS, "&Locations...")
        screenplayMenu.Append(ID_SCREENPLAY_TITLES, "&Title Pages...")
        screenplayMenu.Append(ID_SCREENPLAY_SC_DICT, "&Spell Checker Dictionary...")
        screenplayMenu.AppendSeparator()

        tmp = wx.Menu()

        tmp.Append(ID_SCREENPLAY_SETTINGS_CHANGE, "&Change...")
        tmp.AppendSeparator()
        tmp.Append(ID_SCREENPLAY_SETTINGS_LOAD, "&Load...")
        tmp.Append(ID_SCREENPLAY_SETTINGS_SAVE_AS, "&Save as...")
        screenplayMenu.AppendMenu(ID_SCREENPLAY_SETTINGS, "&Settings", tmp)
        scriptSettingsMenu = tmp

        reportsMenu = wx.Menu()
        reportsMenu.Append(ID_REPORTS_SCRIPT_REP, "Sc&reenplay Report...")
        reportsMenu.Append(ID_REPORTS_LOCATION_REP, "&Location Report...")
        reportsMenu.Append(ID_REPORTS_SCENE_REP, "&Scene Report...")
        reportsMenu.Append(ID_REPORTS_CHARACTER_REP, "&Character Report...")
        reportsMenu.Append(ID_REPORTS_DIALOGUE_CHART, "&Dialogue Chart...")

        toolsMenu = wx.Menu()
        toolsMenu.Append(ID_TOOLS_SPELL_CHECK, "&Spell Checker...\tCTRL-ALT-K")
        toolsMenu.Append(ID_TOOLS_NAME_DB, "&Name Database...")
        toolsMenu.Append(ID_TOOLS_CHARMAP, "&Character Map...")
        toolsMenu.Append(ID_TOOLS_COMPARE_SCRIPTS, "C&ompare Screenplays...")
        toolsMenu.Append(ID_TOOLS_WATERMARK, "&Generate Watermarked PDFs...")

        helpMenu = wx.Menu()
        helpMenu.Append(ID_HELP_COMMANDS, "&Commands...")
        helpMenu.Append(ID_HELP_MANUAL, "&Manual")
        helpMenu.AppendSeparator()
        helpMenu.Append(ID_HELP_ABOUT, "&About...")

        self.menuBar = wx.MenuBar()
        self.menuBar.Append(fileMenu, "&File")
        self.menuBar.Append(editMenu, "&Edit")
        self.menuBar.Append(viewMenu, "&View")
        self.menuBar.Append(screenplayMenu, "Scr&eenplay")
        self.menuBar.Append(reportsMenu, "&Reports")
        self.menuBar.Append(toolsMenu, "Too&ls")
        self.menuBar.Append(helpMenu, "&Help")
        self.SetMenuBar(self.menuBar)

        self.toolBar = self.CreateToolBar(wx.TB_VERTICAL)

        def addTB(id, iconFilename, toolTip):
            self.toolBar.AddLabelTool(
                id, "", misc.getBitmap("resources/%s" % iconFilename),
                shortHelp=toolTip)

        addTB(ID_FILE_NEW, "new.png", "New Screenplay")
        addTB(ID_FILE_OPEN, "open.png", "Open Screenplay")
        addTB(ID_FILE_SAVE, "save.png", "Save")
        addTB(ID_FILE_SAVE_AS, "saveas.png", "Save As")
        addTB(ID_FILE_CLOSE, "close.png", "Close Screenplay")
        addTB(ID_TOOLBAR_SCRIPTSETTINGS, "scrset.png", "Screenplay Settings")
        addTB(ID_FILE_PRINT, "pdf.png", "Print as PDF")

        self.toolBar.AddSeparator()

        addTB(ID_FILE_IMPORT, "import.png", "Import Screenplay")
        addTB(ID_FILE_EXPORT, "export.png", "Export Screenplay")

        self.toolBar.AddSeparator()

        addTB(ID_EDIT_UNDO, "undo.png", "Undo")
        addTB(ID_EDIT_REDO, "redo.png", "Redo")

        self.toolBar.AddSeparator()

        addTB(ID_EDIT_FIND, "find.png", "Find / Replace")
        addTB(ID_TOOLBAR_VIEWS, "layout.png", "View Mode")
        addTB(ID_TOOLBAR_REPORTS, "report.png", "Screenplay Reports")
        addTB(ID_TOOLBAR_TOOLS, "tools.png", "Tools")
        addTB(ID_TOOLBAR_SETTINGS, "settings.png", "Global Settings")

        self.toolBar.SetBackgroundColour(cfgGui.tabBarBgColor)
        self.toolBar.Realize()

        wx.EVT_MOVE(self, self.OnMove)
        wx.EVT_SIZE(self, self.OnSize)

        vsizer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(vsizer)

        hsizer = wx.BoxSizer(wx.HORIZONTAL)

        self.noFSBtn = misc.MyButton(self, -1, "resources/fullscreen.png", getCfgGui)
        self.noFSBtn.SetToolTipString("Exit Fullscreen")
        self.noFSBtn.Show(False)
        hsizer.Add(self.noFSBtn)

        wx.EVT_BUTTON(self, self.noFSBtn.GetId(), self.ToggleFullscreen)

        self.tabCtrl = misc.MyTabCtrl(self, -1, getCfgGui)
        hsizer.Add(self.tabCtrl, 1, wx.EXPAND)

        self.statusCtrl = misc.MyStatus(self, -1, getCfgGui)
        
        # prevent the status widget from hogging the keyboard focus
        wx.EVT_SET_FOCUS(self.statusCtrl, self.OnFocus)
        
        hsizer.Add(self.statusCtrl)

        vsizer.Add(hsizer, 0, wx.EXPAND)

        tmp = misc.MyTabCtrl2(self, -1, self.tabCtrl)
        vsizer.Add(tmp, 1, wx.EXPAND)

        vsizer.Add(wx.StaticLine(self, -1), 0, wx.EXPAND)


        gd.mru.useMenu(fileMenu, 14)

        wx.EVT_MENU_HIGHLIGHT_ALL(self, self.OnMenuHighlight)

        self.tabCtrl.setPageChangedFunc(self.OnPageChange)

        # see OnRightDown
        self.rightClickMenu = wx.Menu()
        self.rightClickMenuWithCut = wx.Menu()

        for m in (self.rightClickMenu, self.rightClickMenuWithCut):
            tmp = wx.Menu()

            tmp.Append(ID_ELEM_TO_SCENE, "&Scene")
            tmp.Append(ID_ELEM_TO_ACTION, "&Action")
            tmp.Append(ID_ELEM_TO_CHARACTER, "&Character")
            tmp.Append(ID_ELEM_TO_PAREN, "&Parenthetical")
            tmp.Append(ID_ELEM_TO_DIALOGUE, "&Dialogue")
            tmp.Append(ID_ELEM_TO_TRANSITION, "&Transition")
            tmp.Append(ID_ELEM_TO_SHOT, "Sh&ot")
            tmp.Append(ID_ELEM_TO_ACTBREAK, "Act &break")
            tmp.Append(ID_ELEM_TO_TITLE, "T&itle")
            tmp.Append(ID_ELEM_TO_NOTE, "&Note")

            m.AppendSubMenu(tmp, "Element type")
            m.AppendSeparator()

            if m is self.rightClickMenuWithCut:
                m.Append(ID_EDIT_CUT, "Cut")
                m.Append(ID_EDIT_COPY, "Copy")

            m.Append(ID_EDIT_PASTE, "Paste")
            m.AppendSeparator()

            if m is self.rightClickMenuWithCut:
                m.Append(ID_EDIT_UPPER, "Make uppercase")

        wx.EVT_MENU(self, ID_FILE_NEW, self.OnNewScript)
        wx.EVT_MENU(self, ID_FILE_OPEN, self.OnOpen)
        wx.EVT_MENU(self, ID_FILE_SAVE, self.OnSave)
        wx.EVT_MENU(self, ID_FILE_SAVE_AS, self.OnSaveScriptAs)
        wx.EVT_MENU(self, ID_FILE_IMPORT, self.OnImportScript)
        wx.EVT_MENU(self, ID_FILE_EXPORT, self.OnExportScript)
        wx.EVT_MENU(self, ID_FILE_CLOSE, self.OnCloseScript)
        wx.EVT_MENU(self, ID_FILE_REVERT, self.OnRevertScript)
        wx.EVT_MENU(self, ID_FILE_PRINT, self.OnPrint)
        wx.EVT_MENU(self, ID_SETTINGS_CHANGE, self.OnSettings)
        wx.EVT_MENU(self, ID_SETTINGS_LOAD, self.OnLoadSettings)
        wx.EVT_MENU(self, ID_SETTINGS_SAVE_AS, self.OnSaveSettingsAs)
        wx.EVT_MENU(self, ID_SETTINGS_SC_DICT, self.OnSpellCheckerDictionaryDlg)
        wx.EVT_MENU(self, ID_FILE_EXIT, self.OnExit)
        wx.EVT_MENU(self, ID_EDIT_UNDO, self.OnUndo)
        wx.EVT_MENU(self, ID_EDIT_REDO, self.OnRedo)
        wx.EVT_MENU(self, ID_EDIT_CUT, self.OnCut)
        wx.EVT_MENU(self, ID_EDIT_COPY, self.OnCopy)
        wx.EVT_MENU(self, ID_EDIT_PASTE, self.OnPaste)
        wx.EVT_MENU(self, ID_EDIT_COPY_TO_CB, self.OnCopySystemCb)
        wx.EVT_MENU(self, ID_EDIT_COPY_TO_CB_FMT, self.OnCopySystemCbFormatted)
        wx.EVT_MENU(self, ID_EDIT_PASTE_FROM_CB, self.OnPasteSystemCb)
        wx.EVT_MENU(self, ID_EDIT_SELECT_SCENE, self.OnSelectScene)
        wx.EVT_MENU(self, ID_EDIT_UPPER, self.OnUpper)
        wx.EVT_MENU(self, ID_EDIT_SELECT_ALL, self.OnSelectAll)
        wx.EVT_MENU(self, ID_EDIT_GO_TO_PAGE, self.OnGotoPage)
        wx.EVT_MENU(self, ID_EDIT_GO_TO_SCENE, self.OnGotoScene)
        wx.EVT_MENU(self, ID_EDIT_INSERT_NBSP, self.OnInsertNbsp)
        wx.EVT_MENU(self, ID_EDIT_FIND, self.OnFind)
        wx.EVT_MENU(self, ID_EDIT_DELETE_ELEMENTS, self.OnDeleteElements)
        wx.EVT_MENU(self, ID_VIEW_STYLE_DRAFT, self.OnViewModeChange)
        wx.EVT_MENU(self, ID_VIEW_STYLE_LAYOUT, self.OnViewModeChange)
        wx.EVT_MENU(self, ID_VIEW_STYLE_SIDE_BY_SIDE, self.OnViewModeChange)
        wx.EVT_MENU(self, ID_VIEW_STYLE_OVERVIEW_SMALL, self.OnViewModeChange)
        wx.EVT_MENU(self, ID_VIEW_STYLE_OVERVIEW_LARGE, self.OnViewModeChange)
        wx.EVT_MENU(self, ID_VIEW_SHOW_FORMATTING, self.OnShowFormatting)
        wx.EVT_MENU(self, ID_VIEW_FULL_SCREEN, self.ToggleFullscreen)
        wx.EVT_MENU(self, ID_VIEW_SHOW_NAVIGATOR, self.OnShowNavigator)
        wx.EVT_MENU(self, ID_SCREENPLAY_FIND_ERROR, self.OnFindNextError)
        wx.EVT_MENU(self, ID_SCREENPLAY_PAGINATE, self.OnPaginate)
        wx.EVT_MENU(self, ID_SCREENPLAY_AUTO_COMPLETION, self.OnAutoCompletionDlg)
        wx.EVT_MENU(self, ID_SCREENPLAY_HEADERS, self.OnHeadersDlg)
        wx.EVT_MENU(self, ID_SCREENPLAY_LOCATIONS, self.OnLocationsDlg)
        wx.EVT_MENU(self, ID_SCREENPLAY_TITLES, self.OnTitlesDlg)
        wx.EVT_MENU(self, ID_SCREENPLAY_SC_DICT,
                    self.OnSpellCheckerScriptDictionaryDlg)
        wx.EVT_MENU(self, ID_SCREENPLAY_SETTINGS_CHANGE, self.OnScriptSettings)
        wx.EVT_MENU(self, ID_SCREENPLAY_SETTINGS_LOAD, self.OnLoadScriptSettings)
        wx.EVT_MENU(self, ID_SCREENPLAY_SETTINGS_SAVE_AS, self.OnSaveScriptSettingsAs)
        wx.EVT_MENU(self, ID_REPORTS_DIALOGUE_CHART, self.OnReportDialogueChart)
        wx.EVT_MENU(self, ID_REPORTS_CHARACTER_REP, self.OnReportCharacter)
        wx.EVT_MENU(self, ID_REPORTS_SCRIPT_REP, self.OnReportScreenplay)
        wx.EVT_MENU(self, ID_REPORTS_LOCATION_REP, self.OnReportLocation)
        wx.EVT_MENU(self, ID_REPORTS_SCENE_REP, self.OnReportScene)
        wx.EVT_MENU(self, ID_TOOLS_SPELL_CHECK, self.OnSpellCheckerDlg)
        wx.EVT_MENU(self, ID_TOOLS_NAME_DB, self.OnNameDatabase)
        wx.EVT_MENU(self, ID_TOOLS_CHARMAP, self.OnCharacterMap)
        wx.EVT_MENU(self, ID_TOOLS_COMPARE_SCRIPTS, self.OnCompareScripts)
        wx.EVT_MENU(self, ID_TOOLS_WATERMARK, self.OnWatermark)
        wx.EVT_MENU(self, ID_HELP_COMMANDS, self.OnHelpCommands)
        wx.EVT_MENU(self, ID_HELP_MANUAL, self.OnHelpManual)
        wx.EVT_MENU(self, ID_HELP_ABOUT, self.OnAbout)

        wx.EVT_MENU_RANGE(self, gd.mru.getIds()[0], gd.mru.getIds()[1],
                          self.OnMRUFile)

        wx.EVT_MENU_RANGE(self, ID_ELEM_TO_ACTION, ID_ELEM_TO_TRANSITION,
                          self.OnChangeType)

        def addTBMenu(id, menu):
            wx.EVT_MENU(self, id, partial(self.OnToolBarMenu, menu=menu))

        addTBMenu(ID_TOOLBAR_SETTINGS, settingsMenu)
        addTBMenu(ID_TOOLBAR_SCRIPTSETTINGS, scriptSettingsMenu)
        addTBMenu(ID_TOOLBAR_REPORTS, reportsMenu)
        addTBMenu(ID_TOOLBAR_VIEWS, viewMenu)
        addTBMenu(ID_TOOLBAR_TOOLS, toolsMenu)

        wx.EVT_CLOSE(self, self.OnCloseWindow)
        wx.EVT_SET_FOCUS(self, self.OnFocus)

        # Cursor blink state and timer.
        self.blinkState = False
        self.cursorTimer = wx.Timer(self)
        wx.EVT_TIMER(self, self.cursorTimer.GetId(), self.OnCursorTimer)

        self.Layout()

    def init(self):
        self.updateKbdCommands()
        self.panel = self.createNewPanel()

    def mySetIcons(self):
        wx.Image_AddHandler(wx.PNGHandler())

        ib = wx.IconBundle()

        for sz in ("16", "32", "64", "128", "256"):
            ib.AddIcon(wx.IconFromBitmap(misc.getBitmap("resources/icon%s.png" % sz)))

        self.SetIcons(ib)

    def allocIds(self):
        names = [
            "ID_EDIT_UNDO",
            "ID_EDIT_REDO",
            "ID_EDIT_COPY",
            "ID_EDIT_COPY_SYSTEM",
            "ID_EDIT_COPY_TO_CB",
            "ID_EDIT_COPY_TO_CB_FMT",
            "ID_EDIT_CUT",
            "ID_EDIT_DELETE_ELEMENTS",
            "ID_EDIT_FIND",
            "ID_EDIT_GO_TO_SCENE",
            "ID_EDIT_GO_TO_PAGE",
            "ID_EDIT_INSERT_NBSP",
            "ID_EDIT_PASTE",
            "ID_EDIT_PASTE_FROM_CB",
            "ID_EDIT_SELECT_ALL",
            "ID_EDIT_SELECT_SCENE",
            "ID_EDIT_UPPER",
            "ID_FILE_CLOSE",
            "ID_FILE_EXIT",
            "ID_FILE_EXPORT",
            "ID_FILE_IMPORT",
            "ID_FILE_NEW",
            "ID_FILE_OPEN",
            "ID_FILE_PRINT",
            "ID_FILE_REVERT",
            "ID_FILE_SAVE",
            "ID_FILE_SAVE_AS",
            "ID_FILE_SETTINGS",
            "ID_HELP_ABOUT",
            "ID_HELP_COMMANDS",
            "ID_HELP_MANUAL",
            "ID_REPORTS_CHARACTER_REP",
            "ID_REPORTS_DIALOGUE_CHART",
            "ID_REPORTS_LOCATION_REP",
            "ID_REPORTS_SCENE_REP",
            "ID_REPORTS_SCRIPT_REP",
            "ID_SCREENPLAY_AUTO_COMPLETION",
            "ID_SCREENPLAY_FIND_ERROR",
            "ID_SCREENPLAY_HEADERS",
            "ID_SCREENPLAY_LOCATIONS",
            "ID_SCREENPLAY_PAGINATE",
            "ID_SCREENPLAY_SC_DICT",
            "ID_SCREENPLAY_SETTINGS",
            "ID_SCREENPLAY_SETTINGS_CHANGE",
            "ID_SCREENPLAY_SETTINGS_LOAD",
            "ID_SCREENPLAY_SETTINGS_SAVE_AS",
            "ID_SCREENPLAY_TITLES",
            "ID_SETTINGS_CHANGE",
            "ID_SETTINGS_LOAD",
            "ID_SETTINGS_SAVE_AS",
            "ID_SETTINGS_SC_DICT",
            "ID_TOOLS_CHARMAP",
            "ID_TOOLS_COMPARE_SCRIPTS",
            "ID_TOOLS_NAME_DB",
            "ID_TOOLS_SPELL_CHECK",
            "ID_TOOLS_WATERMARK",
            "ID_VIEW_SHOW_FORMATTING",
            "ID_VIEW_STYLE_DRAFT",
            "ID_VIEW_STYLE_LAYOUT",
            "ID_VIEW_STYLE_OVERVIEW_LARGE",
            "ID_VIEW_STYLE_OVERVIEW_SMALL",
            "ID_VIEW_STYLE_SIDE_BY_SIDE",
            "ID_TOOLBAR_SETTINGS",
            "ID_TOOLBAR_SCRIPTSETTINGS",
            "ID_TOOLBAR_REPORTS",
            "ID_TOOLBAR_VIEWS",
            "ID_TOOLBAR_TOOLS",
            "ID_VIEW_FULL_SCREEN",
            "ID_VIEW_SHOW_NAVIGATOR",
            "ID_ELEM_TO_ACTION",
            "ID_ELEM_TO_CHARACTER",
            "ID_ELEM_TO_DIALOGUE",
            "ID_ELEM_TO_NOTE",
            "ID_ELEM_TO_PAREN",
            "ID_ELEM_TO_SCENE",
            "ID_ELEM_TO_SHOT",
            "ID_ELEM_TO_ACTBREAK",
            "ID_ELEM_TO_TITLE",
            "ID_ELEM_TO_TRANSITION",
            "ID_NAV_SELECT",
            "ID_NAV_DELETE",
            ]

        g = globals()

        for n in names:
            g[n] = wx.NewId()

        # see OnChangeType
        g["idToLTMap"] = {
            ID_ELEM_TO_SCENE: screenplay.SCENE,
            ID_ELEM_TO_ACTION: screenplay.ACTION,
            ID_ELEM_TO_CHARACTER: screenplay.CHARACTER,
            ID_ELEM_TO_DIALOGUE: screenplay.DIALOGUE,
            ID_ELEM_TO_PAREN: screenplay.PAREN,
            ID_ELEM_TO_TRANSITION: screenplay.TRANSITION,
            ID_ELEM_TO_SHOT: screenplay.SHOT,
            ID_ELEM_TO_ACTBREAK: screenplay.ACTBREAK,
            ID_ELEM_TO_TITLE: screenplay.TITLE,
            ID_ELEM_TO_NOTE: screenplay.NOTE,
            }

    def createNewPanel(self):
        newPanel = MyPanel(self.tabCtrl.getTabParent(), -1)
        self.tabCtrl.addPage(newPanel, u"")
        newPanel.ctrl.setTabText()
        newPanel.ctrl.SetFocus()

        return newPanel

    def setTitle(self, text):
        self.SetTitle("Scrupulous - %s" % text)

    def setTabText(self, panel, text):
        i = self.findPage(panel)

        if i != -1:
            # strip out ".trelby" suffix from tab names (it's a bit
            # complicated since if we open the same file multiple times,
            # we have e.g. "foo.trelby" and "foo.trelby<2>", so actually
            # we just strip out ".trelby" if it's found anywhere in the
            # string)

            s = text.replace(".trelby", "")
            self.tabCtrl.setTabText(i, s)

    # iterates over all tabs and finds out the corresponding page number
    # for the given panel.
    def findPage(self, panel):
        for i in range(self.tabCtrl.getPageCount()):
            p = self.tabCtrl.getPage(i)
            if p == panel:
                return i

        return -1

    # get list of MyCtrl objects for all open screenplays
    def getCtrls(self):
        l = []

        for i in range(self.tabCtrl.getPageCount()):
            l.append(self.tabCtrl.getPage(i).ctrl)

        return l

    # returns True if any open screenplay has been modified
    def isModifications(self):
        modified = []
        for c in self.getCtrls():
            if c.sp.isModified():
                modified.append(c.fileNameDisplay)

        return modified

    def updateKbdCommands(self):
        cfgGl.addShiftKeys()

        if cfgGl.getConflictingKeys() is not None:
            wx.MessageBox("At least one key bound to more than one\n"
                          "command. Fix this.",
                          "Warning", wx.OK, self)

        self.kbdCommands = {}

        for cmd in cfgGl.commands:
            if not (cmd.isFixed and cmd.isMenu):
                for key in cmd.keys:
                    self.kbdCommands[key] = cmd

    def resetTimer(self):
        global t
        if t.isAlive():
            t.cancel()
        t = threading.Timer(cfgGl.autoSaveMinutes * 60, self.autosaveAllScripts)
        if cfgGl.autoSaveMinutes > 0:
            t.start()

    def autosaveAllScripts(self):
        if self.isModifications():
            # try to save every open tab
            count = 1  # track open tabs so we have no naming clashes
            for c in self.getCtrls():
                c.OnAutoSave(count)
                count += 1

        # We want to warn the user if the default screenplay directory is unwritable,
        # but using wx.MessageBox w/code below occasionally crashes with:
        #
        # python: Fatal IO error 11 (Resource temporarily unavailable) on X server :0.
        # This may be related to the use of the timer thread (?) and requires more
        # investigation.  For now, a bad default screenplay directory will result in
        # silent failure as there seems to be no way to safely notify the user.
        #
        # if not os.access(misc.scriptDir, os.W_OK):
        #     wx.MessageBox( "Warning:  No write permission for " + str(misc.scriptDir) +
        #                    ", which is needed to autosave untitled scripts.  " +
        #                    "Change the default screenplay directory in the settings.",
        #                    "Warning", wx.OK, None)

        self.resetTimer()

    # open screenplay, in the current tab if it's untouched, or in a new one
    # otherwise
    # recovery : is this file a recovered file?
    def openScript(self, filename, recovery=False):
        if not self.tabCtrl.getPage(self.findPage(self.panel))\
               .ctrl.isUntouched():
            self.panel = self.createNewPanel()

        self.panel.ctrl.loadFile(filename)
        self.panel.ctrl.updateScreen()
        if recovery:
            self.panel.ctrl.setFile(None)
            self.panel.ctrl.sp.markChanged(True)
        else:
            gd.mru.add(filename)

    def checkFonts(self):
        names = ["Normal", "Bold", "Italic", "Bold-Italic"]
        failed = []

        for i, fi in enumerate(cfgGui.fonts):
            if not util.isFixedWidth(fi.font):
                failed.append(names[i])

        if failed:
            wx.MessageBox(
                "The fonts selected are an unfixed width and\n"
                "will look incorrectly.\n"
                "Change the fonts at File/Settings/Change.\n\n"
                + "\n".join(failed), "Error", wx.OK, self)

    def OnCursorTimer(self, event):
        self.panel.ctrl.DrawCursor(self.blinkState)
        self.blinkState = not self.blinkState

        # Set the timer so that the cursor is shown 2/3rd of the time,
        # and hidden 1/3 of the time.
        if self.blinkState:
            self.cursorTimer.Start(CURSOR_BLINK_RATE // 2)
        else:
            self.cursorTimer.Start(CURSOR_BLINK_RATE)

    # If we get focus, pass it on to ctrl.
    def OnFocus(self, event):
        self.panel.ctrl.SetFocus()

    def OnMenuHighlight(self, event):
        # default implementation modifies status bar, so we need to
        # override it and do nothing
        pass

    def OnPageChange(self, page):
        self.panel = self.tabCtrl.getPage(page)
        self.panel.ctrl.SetFocus()
        self.panel.ctrl.updateCommon()
        self.setTitle(self.panel.ctrl.fileNameDisplay)

    def selectScript(self, toNext):
        current = self.tabCtrl.getSelectedPageIndex()
        pageCnt = self.tabCtrl.getPageCount()

        if toNext:
            pageNr = current + 1
        else:
            pageNr = current - 1

        if pageNr == -1:
            pageNr = pageCnt - 1
        elif pageNr == pageCnt:
            pageNr = 0

        if pageNr == current:
            # only one tab, nothing to do
            return

        self.tabCtrl.selectPage(pageNr)

    def OnScriptNext(self, event=None):
        self.selectScript(True)

    def OnScriptPrev(self, event=None):
        self.selectScript(False)

    def OnNewScript(self, event=None):
        self.panel = self.createNewPanel()

    def OnMRUFile(self, event):
        i = event.GetId() - gd.mru.getIds()[0]
        self.openScript(gd.mru.get(i))

    def OnOpen(self, event=None):
        dlg = wx.FileDialog(self, "Open Screenplay",
            misc.scriptDir,
            wildcard="Trelby screenplays (*.trelby)|*.trelby|All files|*",
            style=wx.OPEN)

        if dlg.ShowModal() == wx.ID_OK:
            misc.scriptDir = dlg.GetDirectory()
            self.openScript(dlg.GetPath())

        dlg.Destroy()

    def OnSave(self, event=None):
        self.panel.ctrl.OnSave()

    def OnSaveScriptAs(self, event=None):
        self.panel.ctrl.OnSaveScriptAs()

    def OnImportScript(self, event=None):
        dlg = wx.FileDialog(self, "Import Screenplay",
            misc.scriptDir,
            wildcard="Importable files (*.txt;*.fdx;*.celtx;*.astx;*.fountain;*.fadein)|" +
                       "*.fdx;*.txt;*.celtx;*.astx;*.fountain;*.fadein|" +
                       "Formatted text files (*.txt)|*.txt|" +
                       "Final Draft XML(*.fdx)|*.fdx|" +
                       "Celtx files (*.celtx)|*.celtx|" +
                       "Adobe Story XML files (*.astx)|*.astx|" +
                       "Fountain files (*.fountain)|*.fountain|" +
                       "Fadein files (*.fadein)|*.fadein|" +
                       "All files|*",
            style=wx.OPEN)

        if dlg.ShowModal() == wx.ID_OK:
            misc.scriptDir = dlg.GetDirectory()

            if not self.tabCtrl.getPage(self.findPage(self.panel))\
                   .ctrl.isUntouched():
                self.panel = self.createNewPanel()

            self.panel.ctrl.importFile(dlg.GetPath())
            self.panel.ctrl.updateScreen()

        dlg.Destroy()

    def OnExportScript(self, event=None):
        self.panel.ctrl.OnExportScript()

    def OnCloseScript(self, event=None):
        if not self.panel.ctrl.canBeClosed():
            return

        if self.tabCtrl.getPageCount() > 1:
            self.tabCtrl.deletePage(self.tabCtrl.getSelectedPageIndex())
        else:
            self.panel.ctrl.createEmptySp()
            self.panel.ctrl.updateScreen()

    def OnRevertScript(self, event=None):
        self.panel.ctrl.OnRevertScript()

    def OnPrint(self, event=None):
        self.panel.ctrl.OnPrint()

    def OnSettings(self, event=None):
        self.panel.ctrl.OnSettings()

    def OnLoadSettings(self, event=None):
        dlg = wx.FileDialog(self, "Open Settings File",
            defaultDir=os.path.dirname(gd.confFilename),
            defaultFile=os.path.basename(gd.confFilename),
            wildcard="Setting files (*.conf)|*.conf|All files|*",
            style=wx.OPEN)

        if dlg.ShowModal() == wx.ID_OK:
            s = util.loadFile(dlg.GetPath(), self)

            if s:
                c = config.ConfigGlobal()
                c.load(s)
                gd.confFilename = dlg.GetPath()

                self.panel.ctrl.applyGlobalCfg(c, False)

        dlg.Destroy()

    def OnSaveSettingsAs(self, event=None):
        dlg = wx.FileDialog(self, "Save Screenplay As",
            defaultDir=os.path.dirname(gd.confFilename),
            defaultFile=os.path.basename(gd.confFilename),
            wildcard="Setting files (*.conf)|*.conf|All files|*",
            style=wx.SAVE | wx.OVERWRITE_PROMPT)

        if dlg.ShowModal() == wx.ID_OK:
            if util.writeToFile(dlg.GetPath(), cfgGl.save(), self):
                gd.confFilename = dlg.GetPath()

        dlg.Destroy()

    def OnUndo(self, event=None):
        self.panel.ctrl.OnUndo()

    def OnRedo(self, event=None):
        self.panel.ctrl.OnRedo()

    def OnUpper(self, event=None):
        self.panel.ctrl.OnUpper()

    def OnCut(self, event=None):
        self.panel.ctrl.OnCut()

    def OnCopy(self, event=None):
        self.panel.ctrl.OnCopy()

    def OnCopySystemCb(self, event=None):
        self.panel.ctrl.OnCopySystem(formatted=False)

    def OnCopySystemCbFormatted(self, event=None):
        self.panel.ctrl.OnCopySystem(formatted=True)

    def OnPaste(self, event=None):
        self.panel.ctrl.OnPaste()

    def OnPasteSystemCb(self, event=None):
        self.panel.ctrl.OnPasteSystemCb()

    def OnSelectScene(self, event=None):
        self.panel.ctrl.OnSelectScene()

    def OnSelectElement(self, event=None):
        self.panel.ctrl.OnSelectElement()

    def OnSelectLine(self, event=None):
        self.panel.ctrl.OnSelectLine()

    def OnSelectWord(self, event=None):
        self.panel.ctrl.OnSelectWord()

    def OnSelectAll(self, event=None):
        self.panel.ctrl.OnSelectAll()

    def OnGotoPage(self, event=None):
        self.panel.ctrl.OnGotoPage()

    def OnGotoScene(self, event=None):
        self.panel.ctrl.OnGotoScene()

    def OnFindNextError(self, event=None):
        self.panel.ctrl.OnFindNextError()

    def OnFind(self, event=None):
        self.panel.ctrl.OnFind()

    def OnInsertNbsp(self, event=None):
        self.panel.ctrl.OnInsertNbsp()

    def OnDeleteElements(self, event=None):
        self.panel.ctrl.OnDeleteElements()

    def OnToggleShowFormatting(self, event=None):
        self.menuBar.Check(ID_VIEW_SHOW_FORMATTING,
            not self.menuBar.IsChecked(ID_VIEW_SHOW_FORMATTING))
        self.showFormatting = not self.showFormatting
        self.panel.ctrl.Refresh(False)

    def OnShowFormatting(self, event=None):
        self.showFormatting = self.menuBar.IsChecked(ID_VIEW_SHOW_FORMATTING)
        self.panel.ctrl.Refresh(False)

    def OnViewModeDraft(self):
        self.menuBar.Check(ID_VIEW_STYLE_DRAFT, True)
        self.OnViewModeChange()

    def OnViewModeLayout(self):
        self.menuBar.Check(ID_VIEW_STYLE_LAYOUT, True)
        self.OnViewModeChange()

    def OnViewModeSideBySide(self):
        self.menuBar.Check(ID_VIEW_STYLE_SIDE_BY_SIDE, True)
        self.OnViewModeChange()

    def OnViewModeOverviewSmall(self):
        self.menuBar.Check(ID_VIEW_STYLE_OVERVIEW_SMALL, True)
        self.OnViewModeChange()

    def OnViewModeOverviewLarge(self):
        self.menuBar.Check(ID_VIEW_STYLE_OVERVIEW_LARGE, True)
        self.OnViewModeChange()

    def OnViewModeChange(self, event=None):
        if self.menuBar.IsChecked(ID_VIEW_STYLE_DRAFT):
            mode = VIEWMODE_DRAFT
        elif self.menuBar.IsChecked(ID_VIEW_STYLE_LAYOUT):
            mode = VIEWMODE_LAYOUT
        elif self.menuBar.IsChecked(ID_VIEW_STYLE_SIDE_BY_SIDE):
            mode = VIEWMODE_SIDE_BY_SIDE
        elif self.menuBar.IsChecked(ID_VIEW_STYLE_OVERVIEW_SMALL):
            mode = VIEWMODE_OVERVIEW_SMALL
        else:
            mode = VIEWMODE_OVERVIEW_LARGE

        gd.setViewMode(mode)

        for c in self.getCtrls():
            c.refreshCache()

        c = self.panel.ctrl
        c.makeLineVisible(c.sp.line)
        c.updateScreen()

    def ToggleFullscreen(self, event=None):
        self.noFSBtn.Show(not self.IsFullScreen())
        self.ShowFullScreen(not self.IsFullScreen(), wx.FULLSCREEN_ALL)
        self.panel.ctrl.SetFocus()

    def OnToggleShowNavigator(self, event=None):
        self.menuBar.Check(ID_VIEW_SHOW_NAVIGATOR,
            not self.menuBar.IsChecked(ID_VIEW_SHOW_NAVIGATOR))
        self.OnShowNavigator(event)

    def OnShowNavigator(self, event=None):
        show = self.menuBar.IsChecked(ID_VIEW_SHOW_NAVIGATOR)
        self.panel.ShowNavigator(show)

    def OnPaginate(self, event=None):
        self.panel.ctrl.OnPaginate()

    def OnAutoCompletionDlg(self, event=None):
        self.panel.ctrl.OnAutoCompletionDlg()

    def OnTitlesDlg(self, event=None):
        self.panel.ctrl.OnTitlesDlg()

    def OnHeadersDlg(self, event=None):
        self.panel.ctrl.OnHeadersDlg()

    def OnLocationsDlg(self, event=None):
        self.panel.ctrl.OnLocationsDlg()

    def OnSpellCheckerDictionaryDlg(self, event=None):
        dlg = spellcheckcfgdlg.SCDictDlg(self, copy.deepcopy(gd.scDict),
                                         True)

        if dlg.ShowModal() == wx.ID_OK:
            gd.scDict = dlg.scDict
            gd.saveScDict()

        dlg.Destroy()

    def OnSpellCheckerScriptDictionaryDlg(self, event=None):
        self.panel.ctrl.OnSpellCheckerScriptDictionaryDlg()

    def OnWatermark(self, event=None):
        self.panel.ctrl.OnWatermark()

    def OnScriptSettings(self, event=None):
        self.panel.ctrl.OnScriptSettings()

    def OnLoadScriptSettings(self, event=None):
        dlg = wx.FileDialog(self, "Open Settings File",
            defaultDir=gd.scriptSettingsPath,
            wildcard="Screenplay Setting Files (*.sconf)|*.sconf|All files|*",
            style=wx.OPEN)

        if dlg.ShowModal() == wx.ID_OK:
            s = util.loadFile(dlg.GetPath(), self)

            if s:
                cfg = config.Config()
                cfg.load(s)
                self.panel.ctrl.applyCfg(cfg)

                gd.scriptSettingsPath = os.path.dirname(dlg.GetPath())

        dlg.Destroy()

    def OnSaveScriptSettingsAs(self, event=None):
        dlg = wx.FileDialog(self, "Save Screenplay Settings As",
            defaultDir=gd.scriptSettingsPath,
            wildcard="Screenplay setting files (*.sconf)|*.sconf|All files|*",
            style=wx.SAVE | wx.OVERWRITE_PROMPT)

        if dlg.ShowModal() == wx.ID_OK:
            if util.writeToFile(dlg.GetPath(), self.panel.ctrl.sp.saveCfg(), self):
                gd.scriptSettingsPath = os.path.dirname(dlg.GetPath())

        dlg.Destroy()

    def OnReportCharacter(self, event=None):
        self.panel.ctrl.OnReportCharacter()

    def OnReportDialogueChart(self, event=None):
        self.panel.ctrl.OnReportDialogueChart()

    def OnReportLocation(self, event=None):
        self.panel.ctrl.OnReportLocation()

    def OnReportScene(self, event=None):
        self.panel.ctrl.OnReportScene()

    def OnReportScreenplay(self, event=None):
        self.panel.ctrl.OnReportScreenplay()

    def OnSpellCheckerDlg(self, event=None):
        self.panel.ctrl.OnSpellCheckerDlg()

    def OnNameDatabase(self, event=None):
        if not namesdlg.readNames(self):
            wx.MessageBox("Cannot open name database.", "Error",
                          wx.OK, self)

            return

        dlg = namesdlg.NamesDlg(self, self.panel.ctrl)
        dlg.ShowModal()
        dlg.Destroy()

    def OnCharacterMap(self, event=None):
        dlg = charmapdlg.CharMapDlg(self, self.panel.ctrl)
        dlg.ShowModal()
        dlg.Destroy()

    def OnCompareScripts(self, event=None):
        self.panel.ctrl.OnCompareScripts()

    def OnChangeType(self, event):
        self.panel.ctrl.OnChangeType(event)

    def OnHelpCommands(self, event=None):
        dlg = commandsdlg.CommandsDlg(cfgGl)
        dlg.Show()

    def OnHelpManual(self, event=None):
        wx.LaunchDefaultBrowser("file://" + misc.getFullPath("manual.html"))

    def OnAbout(self, event=None):
        win = splash.SplashWindow(self, -1)
        win.Show()

    def OnToolBarMenu(self, event, menu):
        self.PopupMenu(menu)

    def OnCloseWindow(self, event):
        doExit = True
        modified = self.isModifications()

        if event.CanVeto() and modified:
            dlg = misc.ExitCancelDlg(self,
                    "UNSAVED changes in these screenplays will be lost:\n\n" +
                    "\n".join(modified) + "\n\n"
                    "Want to dismiss these changes?", "Unsaved Changes")
            if dlg.ShowModal() == wx.CANCEL:
                doExit = False

        if doExit:
            util.writeToFile(gd.stateFilename, gd.save(), self)
            util.removeTempFiles(misc.tmpPrefix)

            # clean recovery files of all open tabs..
            for c in self.getCtrls():
                c.clearRecovery()

            # .. and any other recovery files (previous session, etc)
            for f in util.listRecoveryFiles():
                os.remove(f)

            self.Destroy()
            t.cancel()
            myApp.ExitMainLoop()
        else:
            event.Veto()
            self.OnSave()
            self.Close(True)

    def OnExit(self, event):
        self.Close(False)

    def OnMove(self, event):
        gd.posX, gd.posY = self.GetPositionTuple()
        event.Skip()

    def OnSize(self, event):
        gd.width, gd.height = self.GetSizeTuple()
        event.Skip()

class MyApp(wx.App):

    def OnInit(self):
        global cfgGl, mainFrame, gd, t

        misc.init()

        # check if another instance is running, using the same config path
        instanceName = "Scrupulous-%s" % (misc.confPath)
        self.instance = wx.SingleInstanceChecker(instanceName)
        if self.instance.IsAnotherRunning():
            del self.instance
            wx.MessageBox("Scrupulous is already running.",
                    "Already Running",
                    wx.OK)
            sys.exit()

        if (wx.MAJOR_VERSION != 3) or (wx.MINOR_VERSION != 0):
            wx.MessageBox("An unsupported version\n"
                          "(%s) of wxWidgets was found.\n"
                          "Program needs version 3.0." %
                          wx.VERSION_STRING, "Error", wx.OK)
            sys.exit()

        util.init()

        gd = GlobalData()

        if misc.isWindows:
            major = sys.getwindowsversion()[0]
            if major < 5:
                wx.MessageBox("An unsupported version of Windows\n"
                              "was found. Upgrade to Windows XP\n"
                              "or higher.", "Error", wx.OK)
                sys.exit()

        if not "unicode" in wx.PlatformInfo:
            wx.MessageBox("A non-Unicode build of\n"
                          "wxWidgets was found.",
                          "Error", wx.OK)
            sys.exit()

        # by setting this, we don't have to convert from 8-bit strings to
        # Unicode ourselves everywhere when we pass them to wxWidgets.
        wx.SetDefaultPyEncoding("ISO-8859-1")

        os.chdir(misc.progPath)

        cfgGl = config.ConfigGlobal()
        cfgGl.setDefaults()

        if util.fileExists(gd.confFilename):
            s = util.loadFile(gd.confFilename, None)

            if s:
                cfgGl.load(s)
        else:
            # we want to write out a default config file at startup for
            # various reasons, if no default config file yet exists
            util.writeToFile(gd.confFilename, cfgGl.save(), None)

        refreshGuiConfig()

        # cfgGl.scriptDir is the directory used on startup, while
        # misc.scriptDir is updated every time the user opens something in
        # a different directory.
        misc.scriptDir = cfgGl.scriptDir

        if util.fileExists(gd.stateFilename):
            s = util.loadFile(gd.stateFilename, None)

            if s:
                gd.load(s)

        gd.setViewMode(gd.viewMode)

        if util.fileExists(gd.scDictFilename):
            s = util.loadFile(gd.scDictFilename, None)

            if s:
                gd.scDict.load(s)

        mainFrame = MyFrame(None, -1, "Scrupulous")
        mainFrame.init()

        for arg in opts.filenames:
            mainFrame.openScript(arg)

        mainFrame.Show(True)

        # windows needs this for some reason
        mainFrame.panel.ctrl.SetFocus()

        self.SetTopWindow(mainFrame)

        mainFrame.checkFonts()

        # Check if there are any recovery files, and if present,
        # recover them, else show startup splash.
        r = util.listRecoveryFiles()
        if r:
            wx.MessageBox("Scrupulous did not exit cleanly. The following"
                          "auto-saved screenplays will be recovered.\n\n" +
                          "\n".join(os.path.basename(f) for f in r),
                          "Crash Recovery", wx.OK)
            for f in r:
                mainFrame.openScript(f, recovery=True)

        elif cfgGl.splashTime > 0:
            win = splash.SplashWindow(mainFrame, cfgGl.splashTime * 1000)
            win.Show()
            win.Raise()

        t = threading.Timer(0, mainFrame.resetTimer)
        t.start()

        return True

def main():
    global myApp

    # disable logging or wx may throw up messageboxes about lock files.
    wx.Log.EnableLogging(False)

    opts.init()
    myApp = MyApp(0)
    myApp.MainLoop()
