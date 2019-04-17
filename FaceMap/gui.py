import sys, os, shutil, glob, time
import numpy as np
from PyQt5 import QtGui, QtCore
import pyqtgraph as pg
from pyqtgraph import GraphicsScene
import pims
from FaceMap import facemap, roi
from scipy.stats import zscore, skew
from matplotlib import cm

### custom QDialog which makes a list of items you can include/exclude
class ListChooser(QtGui.QDialog):
    def __init__(self, title, parent):
        super(ListChooser, self).__init__(parent)
        self.setGeometry(300,300,320,320)
        self.setWindowTitle(title)
        self.win = QtGui.QWidget(self)
        layout = QtGui.QGridLayout()
        self.win.setLayout(layout)
        #self.setCentralWidget(self.win)
        layout.addWidget(QtGui.QLabel('(select multiple using ctrl or shift)'),0,0,1,1)
        self.list = QtGui.QListWidget(parent)
        for f in parent.filelist:
            self.list.addItem(f)
        layout.addWidget(self.list,1,0,7,4)
        #self.list.resize(450,250)
        self.list.setSelectionMode(QtGui.QAbstractItemView.MultiSelection)
        done = QtGui.QPushButton('done')
        done.clicked.connect(lambda: self.exit_list(parent))
        layout.addWidget(done,8,0,1,1)

    def exit_list(self, parent):
        parent.filelist = []
        items = self.list.selectedItems()
        for i in range(len(items)):
            parent.filelist.append(str(self.list.selectedItems()[i].text()))
        self.accept()

class Slider(QtGui.QSlider):
    def __init__(self, bid, parent=None):
        super(self.__class__, self).__init__()
        initval = [99,99]
        self.bid = bid
        self.setOrientation(QtCore.Qt.Horizontal)
        self.setMinimum(0)
        self.setMaximum(100)
        self.setValue(initval[bid])
        self.setTickInterval(10)
        self.valueChanged.connect(lambda: self.level_change(parent,bid))
        self.setTracking(False)

    def level_change(self, parent, bid):
        parent.sat[bid] = float(self.value())/100 * 255
        if bid==0:
            parent.pimg.setLevels([0, parent.sat[bid]])
        else:
            #parent.pROIimg.setLevels([0, parent.sat[bid]])
            parent.saturation[parent.iROI] = parent.sat[bid]
            if len(parent.ROIs) > 0:
                parent.ROIs[parent.iROI].plot(parent)
        parent.win.show()

class MainW(QtGui.QMainWindow):
    def __init__(self):
        super(MainW, self).__init__()
        pg.setConfigOptions(imageAxisOrder='row-major')
        self.setGeometry(15,15,1470,1000)
        self.setWindowTitle('FaceMap')
        self.setStyleSheet("QMainWindow {background: 'black';}")
        self.styleUnpressed = ("QPushButton {Text-align: left; "
                               "background-color: rgb(50,50,50); "
                               "color:white;}")
        self.stylePressed = ("QPushButton {Text-align: left; "
                             "background-color: rgb(100,50,100); "
                             "color:white;}")

        self.cwidget = QtGui.QWidget(self)
        self.setCentralWidget(self.cwidget)
        self.l0 = QtGui.QGridLayout()
        #layout = QtGui.QFormLayout()
        self.cwidget.setLayout(self.l0)
        #self.p0 = pg.ViewBox(lockAspect=False,name='plot1',border=[100,100,100],invertY=True)
        self.win = pg.GraphicsLayoutWidget()
        # --- cells image
        self.win = pg.GraphicsLayoutWidget()
        self.win.move(600,0)
        self.win.resize(1000,500)
        self.l0.addWidget(self.win,1,3,27,14)
        layout = self.win.ci.layout

        # A plot area (ViewBox + axes) for displaying the image
        self.p0 = self.win.addViewBox(lockAspect=True,row=0,col=0,invertY=True)
        #self.p0.setMouseEnabled(x=False,y=False)
        self.p0.setMenuEnabled(False)
        self.pimg = pg.ImageItem()
        self.p0.addItem(self.pimg)

        # image ROI
        self.pROI = self.win.addViewBox(lockAspect=True,row=0,col=1,invertY=True)
        #self.p0.setMouseEnabled(x=False,y=False)
        self.pROI.setMenuEnabled(False)
        self.pROIimg = pg.ImageItem()
        self.pROI.addItem(self.pROIimg)
        self.scatter = pg.ScatterPlotItem([0], [0], pen='k', symbol='+')
        self.pROI.addItem(self.scatter)

        # roi initializations
        self.iROI = 0
        self.nROIs = 0
        self.saturation = []
        self.ROIs = []

        # saturation sliders
        self.sl = []
        txt = ["saturation", 'saturation']
        self.sat = [255,255]
        for j in range(2):
            self.sl.append(Slider(j, self))
            self.l0.addWidget(self.sl[j],1,6+5*j,1,2)
            qlabel = QtGui.QLabel(txt[j])
            qlabel.setStyleSheet('color: white;')
            self.l0.addWidget(qlabel,0,6+5*j,1,1)

        self.p1 = self.win.addPlot(name='plot1',row=1,col=0,colspan=2)
        self.p1.setMouseEnabled(x=True,y=False)
        self.p1.setMenuEnabled(False)
        self.p1.setLabel('left', 'plot1')
        #self.p1.autoRange(padding=0.01)
        self.p2 = self.win.addPlot(name='plot2',row=2,col=0,colspan=2)
        self.p2.setMouseEnabled(x=True,y=False)
        self.p2.setMenuEnabled(False)
        self.p2.setLabel('left', 'plot2')
        self.p2.setXLink("plot1")
        #self.p2.autoRange(padding=0.01)
        self.win.ci.layout.setRowStretchFactor(0,5)
        self.movieLabel = QtGui.QLabel("No movie chosen")
        self.movieLabel.setStyleSheet("color: white;")
        self.movieLabel.setAlignment(QtCore.Qt.AlignCenter)
        self.nframes = 0
        self.cframe = 0
        # create ROI chooser
        #qlabel = QtGui.QLabel(self)
        #qlabel.setText("<font color='white'>Selected ROI:</font>")
        #self.l0.addWidget(qlabel,3,0,1,2)
        # create frame slider
        binLabel = QtGui.QLabel("SVD spatial bin:")
        binLabel.setStyleSheet("color: white;")
        self.binSpinBox = QtGui.QSpinBox()
        self.binSpinBox.setRange(1, 20)
        self.binSpinBox.setValue(4)
        self.binSpinBox.setFixedWidth(30)
        self.l0.addWidget(binLabel, 7, 0, 1, 3)
        self.l0.addWidget(self.binSpinBox, 8, 0, 1, 3)
        binLabel = QtGui.QLabel("pupil sigma:")
        binLabel.setStyleSheet("color: white;")
        self.sigmaBox = QtGui.QLineEdit()
        self.sigmaBox.setText("2.5")
        self.sigmaBox.setFixedWidth(45)
        self.l0.addWidget(binLabel, 9, 0, 1, 3)
        self.l0.addWidget(self.sigmaBox, 10, 0, 1, 3)
        self.pupil_sigma = 2.5
        self.sigmaBox.returnPressed.connect(self.pupil_sigma_change)
        self.frameLabel = QtGui.QLabel("Current frame:")
        self.frameLabel.setStyleSheet("color: white;")
        self.frameNumber = QtGui.QLabel("0")
        self.frameNumber.setStyleSheet("color: white;")
        self.frameSlider = QtGui.QSlider(QtCore.Qt.Horizontal)
        #self.frameSlider.setTickPosition(QtGui.QSlider.TicksBelow)
        self.frameSlider.setTickInterval(5)
        self.frameSlider.setTracking(False)
        self.frameDelta = 10
        istretch = 20
        self.createButtons(istretch)
        self.l0.addWidget(QtGui.QLabel(''),istretch,0,1,3)
        self.l0.setRowStretch(istretch,1)
        self.l0.addWidget(self.frameLabel, istretch+3,0,1,3)
        self.l0.addWidget(self.frameNumber, istretch+4,0,1,3)
        self.l0.addWidget(self.frameSlider, istretch+7,3,1,14)

        # plotting boxes
        #pl = QtGui.QLabel("when processed...")
        #pl.setStyleSheet("color: gray;")
        #self.l0.addWidget(pl, 13, 0, 1, 3)
        #pl = QtGui.QLabel("p1")
        #pl.setStyleSheet("color: gray;")
        #self.l0.addWidget(pl, 14, 0, 1, 1)
        #pl = QtGui.QLabel("p2")
        #pl.setStyleSheet("color: gray;")
        #self.l0.addWidget(pl, 14, 1, 1, 1)
        #pl = QtGui.QLabel("roi")
        #pl.setStyleSheet("color: gray;")
        #self.l0.addWidget(pl, 14, 2, 1, 1)
        #self.cbs = []
        #for k in range(6):
        #    self.cbs.append(QtGui.QCheckBox(''))
        #    self.l0.addWidget(self.cbs[-1], 15+k, 0, 1, 1)

        #self.l0.addWidget(QtGui.QLabel(''),17,2,1,1)
        #self.l0.setRowStretch(16,2)
        ll = QtGui.QLabel('play/pause with SPACE')
        ll.setStyleSheet("color: white;")
        self.l0.addWidget(ll,istretch+2,0,1,4)
        #ll = QtGui.QLabel('(when paused, left/right arrow keys can move slider)')
        #ll.setStyleSheet("color: white;")
        #self.l0.addWidget(ll,14,0,1,4)
        self.frameSlider.valueChanged.connect(self.go_to_frame)
        self.l0.addWidget(self.movieLabel,0,0,1,5)
        self.updateFrameSlider()
        self.updateButtons()
        self.updateTimer = QtCore.QTimer()
        self.updateTimer.timeout.connect(self.next_frame)
        self.cframe = 0
        self.loaded = False
        self.Floaded = False
        self.wraw = False
        self.win.scene().sigMouseClicked.connect(self.plot_clicked)
        self.win.show()
        self.show()
        self.processed = False
        #self.load_movies([["/media/carsen/SSD1/cam/cam1_GT3_2019_04_09_1.avi"]])
        #self.openFile(["D:/cams5/mouse_face.mp4"])
        # if not a combined recording, automatically open binary

    def pupil_sigma_change(self):
        self.pupil_sigma = float(self.sigmaBox.text())
        if len(self.ROIs) > 0:
            self.ROIs[self.iROI].plot(self)

    def add_ROI(self):
        roitype = self.comboBox.currentIndex()
        roistr = self.comboBox.currentText()
        if roitype > 0:
            self.saturation.append(255.)
            self.iROI = self.nROIs
            self.ROIs.append(roi.sROI(rind=roitype-1, rtype=roistr, iROI=self.nROIs, parent=self))
            self.nROIs += 1
        else:
            msg = QtGui.QMessageBox(self)
            msg.setIcon(QtGui.QMessageBox.Warning)
            msg.setText("You have to choose an ROI type before creating ROI")
            msg.setStandardButtons(QtGui.QMessageBox.Ok)
            msg.exec_()

    def open_file(self):
        fileName = QtGui.QFileDialog.getOpenFileName(self,
                            "Open movie file")
        # load ops in same folder
        if fileName:
            print(fileName[0])
            self.filelist = [ [fileName[0]] ]
            self.load_movies()

    def open_folder(self):
        folderName = QtGui.QFileDialog.getExistingDirectory(self,
                            "Choose folder with movies")
        # load ops in same folder
        if folderName:
            extensions = ['*.mj2','*.mp4','*.mkv','*.avi','*.mpeg','*.mpg','*.asf']
            fileName = []
            for extension in extensions:
                fileName.extend(glob.glob(folderName+"/"+extension))
            print(fileName[0])
            if len(fileName) > 1:
                self.choose_files(fileName)
                self.load_movies()

    def choose_files(self, fileName):
        self.filelist = fileName
        LC=ListChooser('Choose movies', self)
        result = LC.exec_()
        if len(self.filelist)==0:
            self.filelist=fileName
        if len(self.filelist)>1:
            dm = QtGui.QMessageBox.question(
                self,
                "multiple videos found",
                "Are these videos taken with multiple camera views?",
                QtGui.QMessageBox.Yes | QtGui.QMessageBox.No,
            )
            if dm == QtGui.QMessageBox.Yes:
                print('multi camera view')
                # expects first 4 letters to be different e.g. cam0, cam1, ...
                files = []
                iview = [os.path.basename(self.filelist[0])[:4]]
                for f in self.filelist[1:]:
                    fbeg = os.path.basename(f)[:4]
                    inview = np.array([iv==fbeg for iv in iview])
                    if inview.sum()==0:
                        iview.append(fbeg)
                print(iview)
                for k in range(len(iview)):
                    ij = 0
                    for f in self.filelist:
                        if iview[k] == os.path.basename(f)[:4]:
                            if k==0:
                                files.append([])
                            files[ij].append(f)
                            ij +=1
                self.filelist = files
            else:
                print('single camera')

        print(self.filelist)
        

    def open_proc(self):
        fileName = QtGui.QFileDialog.getOpenFileName(self,
                        "Open processed file", filter="*.npy")
        self.openProc(fileName[0])

    def openProc(self, fileName):
        try:
            proc = np.load(fileName)
            proc = proc.item()
            self.filenames = proc['filenames']
            good=True
        except:
            print("ERROR: not a processed movie file")
        if good:
            v = []
            nframes = 0
            iframes = []
            for file in self.filenames:
                v.append(pims.Video(file))
                iframes.append(len(v[-1]))
                nframes += len(v[-1])
            self.motSVD = proc['motSVD']
            self.motSVD *= np.sign(skew(self.motSVD, axis=0))[np.newaxis,:]
            self.motStd = self.motSVD.std(axis=0)
            self.video = v
            self.nframes = nframes
            self.iframes = np.array(iframes).astype(int)
            self.Ly = self.video[0].frame_shape[0]
            self.Lx = self.video[0].frame_shape[1]
            self.p1.clear()
            self.p2.clear()
            self.process.setEnabled(True)
            # get scaling from 100 random frames
            #rperm = np.random.permutation(nframes)
            #frames = np.zeros((self.Ly,self.Lx,100))
            #for r in range(100):
            #    frames[:,:,r] = np.array(self.video[0][rperm[r]]).mean(axis=-1)
            #self.srange = (frames.mean() + frames.std()*np.array([-3,3])).astype(int)
            #self.srange = [np.percentile(frames.flatten(),8), np.percentile(frames.flatten(),99)]
            self.movieLabel.setText(self.filenames[0])
            self.nbytesread = 2 * self.Ly * self.Lx
            self.frameDelta = int(np.maximum(5,self.nframes/200))
            self.frameSlider.setSingleStep(self.frameDelta)
            if self.nframes > 0:
                self.updateFrameSlider()
                self.updateButtons()
            self.cframe = -1
            self.loaded = True
            self.processed = True
            self.plot_processed()
            self.next_frame()

    def load_movies(self, filelist=None):
        if filelist is not None:
            self.filelist = filelist
        try:
            v = []
            nframes = 0
            iframes = []
            cumframes = [0]
            k=0
            for fs in self.filelist:
                vs = []
                for f in fs:
                    vs.append(pims.Video(f))
                v.append(vs)
                iframes.append(len(v[-1][0]))
                cumframes.append(cumframes[-1] + len(v[-1][0]))
                nframes += len(v[-1][0])
                if k==0:
                    Ly = []
                    Lx = []
                    for vs in v[-1]:
                        fshape = vs.frame_shape
                        Ly.append(fshape[0])
                        Lx.append(fshape[1])
                k+=1
            good = True
        except Exception as e:
            print("ERROR: not a supported movie file")
            print(e)
            good = False
        if good:
            self.video = v
            self.filenames = self.filelist
            self.nframes = nframes
            self.iframes = np.array(iframes).astype(int)
            self.cumframes = np.array(cumframes).astype(int)
            self.Ly = Ly
            self.Lx = Lx
            self.p1.clear()
            self.p2.clear()
            self.process.setEnabled(True)
            if len(self.Ly)<2:
                self.LY = self.Ly[0]
                self.LX = self.Lx[0]
                self.sx = np.array([int(0)])
                self.sy = np.array([int(0)])
                self.vmap = np.zeros((self.LY,self.LX), np.int32)
            else:
                # make placement of movies
                Ly = np.array(self.Ly.copy())
                Lx = np.array(self.Lx.copy())
                npix = Ly * Lx
                picked = np.zeros((Ly.size,), np.bool)
                ly = 0
                lx = 0
                sy = np.zeros(Ly.shape, int)
                sx = np.zeros(Lx.shape, int)
                if Ly.size==2:
                    gridy = 1
                    gridx = 2
                elif Ly.size==3:
                    gridy = 1
                    gridx = 2
                else:
                    gridy = int(np.round(Ly.size**0.5 * 0.75))
                    gridx = int(np.ceil(Ly.size / gridy))
                LY = 0
                LX = 0
                iy = 0
                ix = 0
                while (~picked).sum() > 0:
                    # place biggest movie first
                    npix0 = npix.copy()
                    npix0[picked] = 0
                    imax = np.argmax(npix0)
                    picked[imax] = 1
                    if iy==0:
                        ly = 0
                        rowmax=0
                    if ix==0:
                        lx = 0
                    sy[imax] = ly
                    sx[imax] = lx
                    
                    ly+=Ly[imax]
                    rowmax = max(rowmax, Lx[imax])
                    if iy==gridy-1 or (~picked).sum()==0:
                        lx+=rowmax
                    LY = max(LY, ly)
                    iy+=1
                    if iy >= gridy:
                        iy = 0
                        ix += 1
                LX = lx
                print(LY, LX)
                self.vmap = -1 * np.ones((LY,LX), np.int32)
                for i in range(Ly.size):
                    self.vmap[np.ix_(np.arange(sy[i], sy[i]+Ly[i], 1, int),
                                     np.arange(sx[i], sx[i]+Lx[i], 1, int))] = i
                self.sy = sy
                self.sx = sx
                self.LY = LY
                self.LX = LX
                
            self.fullimg = np.zeros((self.LY, self.LX, 3))
            self.imgs = []
            self.img = []
            for i in range(len(self.Ly)):
                self.imgs.append(np.zeros((self.Ly[i], self.Lx[i], 3, 3)))
                self.img.append(np.zeros((self.Ly[i], self.Lx[i], 3)))
            self.srange = []
            # get scaling from 100 random frames in the first video
            for n in range(len(self.Ly)):
                rperm = np.random.permutation(iframes[0])
                frames = np.zeros((self.Ly[n],self.Lx[n], min(40, iframes[0]-1)))
                for r in range(frames.shape[-1]):
                    frames[:,:,r] = np.array(self.video[0][n][rperm[r]]).mean(axis=-1)
                self.srange.append(frames.mean() + frames.std()*np.array([-3,3]))
            self.movieLabel.setText(os.path.dirname(self.filenames[0][0]))
            self.frameDelta = int(np.maximum(5,self.nframes/200))
            self.frameSlider.setSingleStep(self.frameDelta)
            if self.nframes > 0:
                self.updateFrameSlider()
                self.updateButtons()
            self.cframe = 1
            self.loaded = True
            self.processed = False
            self.jump_to_frame()


    def keyPressEvent(self, event):
        bid = -1
        if self.playButton.isEnabled():
            if event.modifiers() !=  QtCore.Qt.ShiftModifier:
                if event.key() == QtCore.Qt.Key_Left:
                    self.cframe -= self.frameDelta
                    self.cframe  = np.maximum(0, np.minimum(self.nframes-1, self.cframe))
                    self.frameSlider.setValue(self.cframe)
                elif event.key() == QtCore.Qt.Key_Right:
                    self.cframe += self.frameDelta
                    self.cframe  = np.maximum(0, np.minimum(self.nframes-1, self.cframe))
                    self.frameSlider.setValue(self.cframe)
        if event.modifiers() != QtCore.Qt.ShiftModifier:
            if event.key() == QtCore.Qt.Key_Space:
                if self.playButton.isEnabled():
                    # then play
                    self.start()
                else:
                    self.pause()

    def plot_clicked(self,event):
        items = self.win.scene().items(event.scenePos())
        posx  = 0
        posy  = 0
        iplot = 0
        zoom = False
        zoomImg = False
        choose = False
        if self.loaded:
            for x in items:
                if x==self.p1:
                    vb = self.p1.vb
                    pos = vb.mapSceneToView(event.scenePos())
                    posx = pos.x()
                    iplot = 1
                elif x==self.p2:
                    vb = self.p1.vb
                    pos = vb.mapSceneToView(event.scenePos())
                    posx = pos.x()
                    iplot = 2
                elif x==self.p0:
                    if event.button()==1:
                        if event.double():
                            zoomImg=True
                if iplot==1 or iplot==2:
                    if event.button()==1:
                        if event.double():
                            zoom=True
                        else:
                            choose=True
        if zoomImg:
            self.p0.setRange(xRange=(0,self.LX),yRange=(0,self.LY))
            
        if zoom:
            self.p1.setRange(xRange=(0,self.nframes))
        if choose:
            if self.playButton.isEnabled():
                self.cframe = np.maximum(0, np.minimum(self.nframes-1, int(np.round(posx))))
                self.frameSlider.setValue(self.cframe)
                #self.jump_to_frame()

    def go_to_frame(self):
        self.cframe = int(self.frameSlider.value())
        self.jump_to_frame()

    def fitToWindow(self):
        self.movieLabel.setScaledContents(self.fitCheckBox.isChecked())

    def updateFrameSlider(self):
        self.frameSlider.setMaximum(self.nframes-1)
        self.frameSlider.setMinimum(0)
        self.frameLabel.setEnabled(True)
        self.frameSlider.setEnabled(True)

    def updateButtons(self):
        self.playButton.setEnabled(True)
        self.pauseButton.setEnabled(False)
        self.addROI.setEnabled(True)
        self.pauseButton.setChecked(True)

    def createButtons(self, istretch):
        iconSize = QtCore.QSize(20, 20)
        openButton = QtGui.QToolButton()
        openButton.setIcon(self.style().standardIcon(QtGui.QStyle.SP_FileIcon))
        openButton.setIconSize(iconSize)
        openButton.setToolTip("Open single movie file")
        openButton.clicked.connect(self.open_file)

        openButton2 = QtGui.QToolButton()
        openButton2.setIcon(self.style().standardIcon(QtGui.QStyle.SP_DialogOpenButton))
        openButton2.setIconSize(iconSize)
        openButton2.setToolTip("Open movie folder")
        openButton2.clicked.connect(self.open_folder)

        openButton3 = QtGui.QToolButton()
        openButton3.setIcon(self.style().standardIcon(QtGui.QStyle.SP_FileDialogStart))
        openButton3.setIconSize(iconSize)
        openButton3.setToolTip("Open processed file")
        openButton3.clicked.connect(self.open_proc)

        iconSize = QtCore.QSize(30, 30)
        self.process = QtGui.QPushButton('process ROIs')
        self.process.setFont(QtGui.QFont("Arial", 8, QtGui.QFont.Bold))
        #self.process.setIcon(self.style().standardIcon(QtGui.QStyle.SP_ComputerIcon))
        #self.process.setIconSize(iconSize)
        #self.process.setToolTip("Process ROIs")
        self.process.clicked.connect(self.process_ROIs)
        self.process.setEnabled(False)

        self.playButton = QtGui.QToolButton()
        self.playButton.setIcon(self.style().standardIcon(QtGui.QStyle.SP_MediaPlay))
        self.playButton.setIconSize(iconSize)
        self.playButton.setToolTip("Play")
        self.playButton.setCheckable(True)
        self.playButton.clicked.connect(self.start)

        self.pauseButton = QtGui.QToolButton()
        self.pauseButton.setCheckable(True)
        self.pauseButton.setIcon(self.style().standardIcon(QtGui.QStyle.SP_MediaPause))
        self.pauseButton.setIconSize(iconSize)
        self.pauseButton.setToolTip("Pause")
        self.pauseButton.clicked.connect(self.pause)

        btns = QtGui.QButtonGroup(self)
        btns.addButton(self.playButton,0)
        btns.addButton(self.pauseButton,1)
        btns.setExclusive(True)

        quitButton = QtGui.QToolButton()
        quitButton.setIcon(self.style().standardIcon(QtGui.QStyle.SP_DialogCloseButton))
        quitButton.setIconSize(iconSize)
        quitButton.setToolTip("Quit")
        quitButton.clicked.connect(self.close)

        self.comboBox = QtGui.QComboBox(self)
        self.comboBox.setFixedWidth(80)
        self.comboBox.addItem("ROI type")
        self.comboBox.addItem("pupil")
        self.comboBox.addItem("motion SVD")
        self.comboBox.addItem("blink")
        self.comboBox.addItem("running")
        self.newROI = 0
        self.comboBox.setCurrentIndex(0)
        #self.comboBox.currentIndexChanged.connect(self.mode_change)

        self.addROI = QtGui.QPushButton("add ROI")
        self.addROI.setFont(QtGui.QFont("Arial", 8, QtGui.QFont.Bold))
        self.addROI.clicked.connect(self.add_ROI)
        self.addROI.setEnabled(False)

        self.checkBox = QtGui.QCheckBox("Compute full SVD")
        self.checkBox.setStyleSheet("color: white;")
        self.checkBox.toggle()

        self.l0.addWidget(openButton,1,0,1,1)
        self.l0.addWidget(openButton2,1,1,1,1)
        self.l0.addWidget(openButton3,1,2,1,1)
        self.l0.addWidget(self.comboBox, 2, 0, 1, 3)
        self.l0.addWidget(self.addROI,3,0,1,3)
        self.l0.addWidget(self.checkBox, 11, 0, 1, 3)
        self.l0.addWidget(self.process,12,0,1,3)
        self.l0.addWidget(self.playButton,istretch+7,0,1,1)
        self.l0.addWidget(self.pauseButton,istretch+7,1,1,1)
        #self.l0.addWidget(quitButton,0,1,1,1)
        self.playButton.setEnabled(False)
        self.pauseButton.setEnabled(False)
        self.pauseButton.setChecked(True)

    def jump_to_frame(self):
        if self.playButton.isEnabled():
            self.cframe = np.maximum(0, np.minimum(self.nframes-1, self.cframe))
            self.cframe = int(self.cframe)
            self.cframe -= 1
            self.img = self.get_frame(self.cframe)
            for i in range(len(self.img)):
                self.imgs[i][:,:,:,1] = self.img[i].copy()
            img = self.get_frame(self.cframe+1)
            for i in range(len(self.img)):
                self.imgs[i][:,:,:,2] = img[i]
            self.next_frame()

    def get_frame(self, cframe):
        cframe = np.maximum(0, np.minimum(self.nframes-1, cframe))
        cframe = int(cframe)
        try:
            ivid = (self.cumframes < cframe).nonzero()[0][-1]
        except:
            ivid = 0
        img = []
        for vs in self.video[ivid]:
            img.append(np.array(vs[cframe - self.cumframes[ivid]]))
        return img

    def next_frame(self):
        # loop after video finishes
        self.cframe+=1
        if self.cframe > self.nframes - 1:
            self.cframe = 0
        for i in range(len(self.imgs)):
            self.imgs[i][:,:,:,:2] = self.imgs[i][:,:,:,1:]
        im = self.get_frame(self.cframe+1)
        for i in range(len(self.imgs)):
            self.imgs[i][:,:,:,2] = im[i]
            self.img[i] = self.imgs[i][:,:,:,1].copy()
            self.fullimg[np.ix_(np.arange(self.sy[i], self.sy[i]+self.Ly[i], 1, int),
                                np.arange(self.sx[i], self.sx[i]+self.Lx[i], 1, int),
                                np.arange(0, 3, 1, int))] = self.img[i]#(self.img[i].astype(np.float32) - self.srange[i][0]) / (self.img[i] - self.srange[i][1]) * 255
        
        if len(self.ROIs) > 0:
            self.ROIs[self.iROI].plot(self)
        #if self.Floaded:
        #    self.img[self.yext,self.xext,0] = self.srange[0]
        #    self.img[self.yext,self.xext,1] = self.srange[0]
        #    self.img[self.yext,self.xext,2] = (self.srange[1]) * np.ones((self.yext.size,),np.float32)
        
        self.pimg.setImage(self.fullimg)
        self.pimg.setLevels([0,self.sat[0]])
        #self.pROIimg.setLevels([0,self.sat[1]])
        self.frameSlider.setValue(self.cframe)
        self.frameNumber.setText(str(self.cframe))
        if self.processed:
            self.scatter1.setData([self.cframe, self.cframe],
                                   [self.motSVD[self.cframe, 0],
                                   self.motSVD[self.cframe, 1]],
                                   size=10,brush=pg.mkBrush(255,255,255))
            #self.scatter2.setData([self.cframe, self.cframe],
            #                      [self.motSVD[self.cframe, 0] / self.motStd[0],
            #                      self.motSVD[self.cframe, 1]] / self.motStd[1],
            #                      size=10,brush=pg.mkBrush(255,255,255))

    def start(self):
        if self.cframe < self.nframes - 1:
            #print('playing')
            self.playButton.setEnabled(False)
            self.pauseButton.setEnabled(True)
            self.frameSlider.setEnabled(False)
            self.updateTimer.start(25)

    def pause(self):
        self.updateTimer.stop()
        self.playButton.setEnabled(True)
        self.pauseButton.setEnabled(False)
        self.frameSlider.setEnabled(True)
        #print('paused')

    def process_ROIs(self):
        self.sbin = int(self.binSpinBox.value())
        self.motSVDs, self.pupils, self.running = facemap.run(self.filenames, self)
        self.processed = True
        if fullSVD:
            self.motSVD = self.motSVDs[0]
            print(self.motSVD.shape)
            self.motSVD *= np.sign(skew(self.motSVD, axis=0))[np.newaxis,:]
            self.motStd = self.motSVD.std(axis=0)
        elif len(self.motSVDs) > 1:
            self.motSVD = self.motSVDs[1]
            print(self.motSVD.shape)
            self.processed = True
            self.motSVD *= np.sign(skew(self.motSVD, axis=0))[np.newaxis,:]
            self.motStd = self.motSVD.std(axis=0)
        if 'area' in self.pupils[0]:
            self.pup = self.pupils[0]['area']
        self.plot_processed()

    def plot_processed(self):
        self.cframe = 0
        self.p1.clear()
        self.p2.clear()
        cmap = cm.get_cmap("hsv")
        nc = min(8,self.motSVD.shape[1])
        cmap = (255 * cmap(np.linspace(0,0.8,nc))).astype(int)
        for c in range(nc):
            #self.p1.plot(self.motSVD[:, c],  pen=tuple(cmap[c,:]))
            self.p1.plot(self.motSVD[:, c] / self.motStd[c],  pen=tuple(cmap[c,:]))

        motScale = self.motSVD[:,:nc] / self.motStd[:nc][np.newaxis,:]
        self.p1.setRange(xRange=(0,self.nframes),
                         yRange=(motScale.min(), motScale.max()),
                          padding=0.0)
        self.p1.setLimits(xMin=0,xMax=self.nframes)

        self.scatter1 = pg.ScatterPlotItem()
        self.p1.addItem(self.scatter1)
        self.scatter1.setData([self.cframe, self.cframe],
                              [self.motSVD[self.cframe, 0] / self.motStd[0],
                              self.motSVD[self.cframe, 1]] / self.motStd[1],
                              size=10,brush=pg.mkBrush(255,255,255))

        self.p2.setLimits(xMin=0,xMax=self.nframes)
        self.scatter2 = pg.ScatterPlotItem()
        self.p2.addItem(self.scatter2)
        for p in range(len(self.pupils)):
            pup = self.pupils[p]
            self.p2.plot(zscore(pup['area']))
            self.p2.plot(zscore(pup['com'][:,0]))
            self.p2.plot(zscore(pup['com'][:,1]))
            self.p2.setRange(xRange=(0,self.nframes),
                             yRange=(-2, 4),
                             padding=0.0)
        #self.scatter2.setData([self.cframe, self.cframe],
        #                       [self.motSVD[self.cframe, 0],
        #                       self.motSVD[self.cframe, 1]],
        #                       size=10,brush=pg.mkBrush(255,255,255))

        self.jump_to_frame()

    def button_status(self, status):
        self.playButton.setEnabled(status)
        self.pauseButton.setEnabled(status)
        self.frameSlider.setEnabled(status)
        self.process.setEnabled(status)

def run():
    # Always start by initializing Qt (only once per application)
    app = QtGui.QApplication(sys.argv)
    # icon_path = os.path.join(
    #     os.path.dirname(os.path.realpath(__file__)), "logo/logo.png"
    # )
    # app_icon = QtGui.QIcon()
    # app_icon.addFile(icon_path, QtCore.QSize(16, 16))
    # app_icon.addFile(icon_path, QtCore.QSize(24, 24))
    # app_icon.addFile(icon_path, QtCore.QSize(32, 32))
    # app_icon.addFile(icon_path, QtCore.QSize(48, 48))
    # app_icon.addFile(icon_path, QtCore.QSize(96, 96))
    # app_icon.addFile(icon_path, QtCore.QSize(256, 256))
    # app.setWindowIcon(app_icon)
    GUI = MainW()
    #p = GUI.palette()
    ret = app.exec_()
    # GUI.save_gui_data()
    sys.exit(ret)


# run()