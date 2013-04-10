function mazeClient()
    
    % Check existence and add (if necessary) the dependencies folder to MATLAB path
    dependenciesFolder = 'deps/';
    if isempty( strfind( path, dependenciesFolder ) ),
        disp( ['Adding the local dependencies dir [' dependenciesFolder ' ] to path'] );
        addpath( dependenciesFolder );
    else
        disp( ['The local dependencies dir [' dependenciesFolder '] is already in the path.'] );
    end

    logThis( [], 'logCallerInfo', false );
    
    moduleName                      = 'SSVEPmazeClient';
    moduleVersion                   = '14';
    subjectName                     = 'Happy Player';
    frequencyList                   = [15 12 10 8.57];
    saveLog                         = true;
    showLog                         = true;
    updateReport                    = true;
    debugMode                       = false;
    experimentMode                  = true;
    godMode                         = false;
    useOnOffStimulation             = false;
    ssvepWindowSize                 = 3;  % seconds
    nHarmonics                      = 3;
    reclassificationInterval        = .2;  % seconds
    queueSize                       = 9;
    BCIserverAddress                = 'localhost';
    BCIserverPort                   = 9000;
    avatarSpeed                     = 1; % cells/second
    nFramesForPTBtest               = 200;
    
    defaultChannelNameList          = { 'P4' 'Pz' 'P4' 'PO9' 'O1' 'Oz' 'O2' 'PO10'};
    eegChannelsSetupData            = [];
    eegTargetChannelListString      = 'all';
    targetChannelList               = 1:numel( defaultChannelNameList );
    
    showQueue                       = true;
    queueUpperWeight                = 1;
    queueLowerWeight                = .08;
    showQueueText                   = false;
    treatAllCellsAsDecisionCells    = false;
    markCorrectDecisions            = true;
    markDecisionCells               = false;
    arrowsOnPeriphery               = true; false;
    showDecision                    = true;
    showOnlyPossibleMoves           = true;
    useOnlyPossibleMoves            = true;
    initialAvatarSize               = 160;
    stimulusSize                    = 350;
    
    gameStartTime                   = 0;
    gameStopTime                    = 0;
    specialCellLabel                = 2;
    decisionCellLabel               = 1;
    startCellLabel                  = -1;
    exitCellLabel                   = -2;

    commandList     = '12340'; % 'LURDS'; %'LRUD';
    nCommands       = numel( commandList );
    iCommandGoLeft  = 1;
    iCommandGoUp    = 2;
    iCommandGoRight = 3;
    iCommandGoDown  = 4;
    iCommandStay    = 5;
    
    commandGoLeftChar  = commandList(iCommandGoLeft);
    commandGoUpChar    = commandList(iCommandGoUp);
    commandGoRightChar = commandList(iCommandGoRight);
    commandGoDownChar  = commandList(iCommandGoDown);
    commandStayChar    = commandList(iCommandStay);
    
    %-------------------------------------------------------------------------
    % game mode
    gameMode = { 'experiment' 'free play' };
    
    parameterList = {
        'BCI server address'    BCIserverAddress    'BCIserverAddress'
        'BCI server port'       BCIserverPort       'BCIserverPort'
        'Game mode'             gameMode            'gameMode'
        };
    
    while true,
        
        % update parameters from GUI
        initialPars = getItFromGUI( ...
            parameterList(:,1)', ...    list of parameter descriptions (cell array of strings)
            parameterList(:,2)', ...    list of default values for each parameter
            parameterList(:,3)', ...    list of variables to update
            'mazeConnectionPrefs', ...  name of preference group (to save parameter values for the next Round)
            '"The Maze" server connection data' ...
            );        
 
        con = pnet('tcpconnect', BCIserverAddress, BCIserverPort);
        if con >= 0
            break;
        end        
        logThis( 'Let''s do it again...' );        
    end % of connection loop
    
    experimentMode = strcmpi( 'experiment', gameMode );
    
    % Do a test ping with the server
    pnet(con, 'printf', 'PING\r\n');
    wait_for_message(con, 'PONG');
        
    pnet(con, 'printf', 'DEVICE GET\r\n' );
    res = tokenize_message(con);
    eegDeviceList = res(3:end); % Disregard DEVICE PRODIVE bit
    
    %-------------------------------------------------------------------------
    % setup GUI parameters

    classifier = {'MNEC', 'canoncorr'};
    parameterList = {
        'Subject name'                                  subjectName                     'subjectName'
        'EEG device'                                    eegDeviceList                   'eegDeviceName'
        'Target EEG channels (default 0=all)'           eegTargetChannelListString      'eegTargetChannelListString'
        'Stimulation frequency list'                    frequencyList                   'frequencyList'
        'Classifier algorithm'                          classifier                      'classifier'
        'SSVEP window size (seconds)'                   ssvepWindowSize                 'ssvepWindowSize'
        'Number of harmonics (including f0)'            nHarmonics                      'nHarmonics'
        'Reclassification period (seconds)'             reclassificationInterval        'reclassificationInterval'
        'Decision queue size'                           queueSize                       'queueSize'
        'Avatar speed (cells/second)'                   avatarSpeed                     'avatarSpeed'
        'Number of frames PTB sync test'                nFramesForPTBtest               'nFramesForPTBtest'
        'Initial avatar size [px]'                      initialAvatarSize               'initialAvatarSize'
        'Stimulus (arrow) size [px]'                    stimulusSize                    'stimulusSize'
        'Weight of the last decision in the queue'      queueUpperWeight                'queueUpperWeight'
        'Weight of the oldest decision in the queue'    queueLowerWeight                'queueLowerWeight'
        'Debug mode (windowed)'                         debugMode                       'debugMode'
        'Use binary (on/off) stimulation'               useOnOffStimulation             'useOnOffStimulation'
        'God mode (iddqd)'                              godMode                         'godMode'
        'Show the decision queue (graphically)'         showQueue                       'showQueue'
        'Show the decision queue in console'            showQueueText                   'showQueueText'
        'Show the actual decision'                      showDecision                    'showDecision'
        'Mark decision cells in maze'                   markDecisionCells               'markDecisionCells'
        'Mark correct decisions (only in experiment)'   markCorrectDecisions            'markCorrectDecisions'
        'Treat all cells as decision cells'             treatAllCellsAsDecisionCells    'treatAllCellsAsDecisionCells'
        'Put arrows on periphery of the maze'           arrowsOnPeriphery               'arrowsOnPeriphery'
        'Show only possible moves (arrows)'             showOnlyPossibleMoves           'showOnlyPossibleMoves'
        'Use only possible moves (arrows)'              useOnlyPossibleMoves            'useOnlyPossibleMoves'
        'Show log in console output'                    showLog                         'showLog'
        'Save log to a file'                            saveLog                         'saveLog'
        'Update report file (only in experiment)'       updateReport                    'updateReport'
        };
    
    
    prefGroupName = [moduleName '_v' moduleVersion];
    prefGroupName( prefGroupName < '0') = '_';
    
    % update parameters from GUI
    mazeParameters = getItFromGUI( ...
        parameterList(:,1)', ...    list of parameter descriptions (cell array of strings)
        parameterList(:,2)', ...    list of default values for each parameter
        parameterList(:,3)', ...    list of variables to update
        prefGroupName, ...          name of preference group (to save parameter values for the next Round)
        'Please, input parameters for The Maze' ...
        );
    
    if isempty( mazeParameters ),
        pnet(con, 'close');
        return
    end
    
    
    %-------------------------------------------------------------------------
    % init hostName
    if isunix,
        hostName = lower( strtok( getenv( 'HOSTNAME' ), '.' ) );
    else
        hostName = lower( strtok( getenv( 'COMPUTERNAME' ), '.' ) );
    end
    
    %-------------------------------------------------------------------------
    if saveLog,
        if experimentMode,
            logDir = './logs/experiments/';
        else
            logDir = './logs/games/';
        end
        
        if ~exist( logDir, 'dir' ),
            mkdir( logDir );
        end        
        currentTimeString = datestr( now(), 'yyyy-mm-dd-HH-MM-SS' );
        if ~exist( 'subjectName', 'var' ) || isempty( subjectName ),
            subjectName = 'The Maze happy player';
        end
        subjectTag = strrep( compactString( subjectName ), ' ', '-' );
        logFilename = [logDir currentTimeString '-' subjectTag '-The-Maze-client-log.txt'];
        logThis( [], 'logToFile', saveLog, 'logFilename', logFilename );
    end % of sevelog branch

    logThis( [], 'logToScreen', showLog );
    
    possibleMoveIntensities = [0.2 1];
    
    disableWrongMoves       = experimentMode;
    flushDecisionQueueOnMistake = disableWrongMoves;
    
    markSpecialCells        = false; true;
    avatarCanMove           = true;
    
    decisionThreshold       = queueSize * (queueUpperWeight + queueLowerWeight) / 4;
    nFrequencies            = numel( frequencyList );
    nStimuli                = nFrequencies;
    possibleMoveMasks       = ones( 1, nStimuli );
    
    if debugMode,
        markSpecialCells    = true;
        markDecisionCells   = true;
        stimulusSize        = 100;
        reclassificationInterval = .2;  % seconds
    end
    
    phases = zeros( size( frequencyList ) ); %#ok<NASGU>
    
    queueWeightList = linspace( queueUpperWeight, queueLowerWeight, queueSize );
    tagExperiment = sprintf( 'SSVEP-based maze game (%s)', subjectName );
    
    logThis( 'Hello, I am the SSVEP-maze client ' )
    
    %------------------------------------------------

    logThis( 'Sending data to BCI server' );
    pnet(con, 'printf', 'DEVICE SET "%s"\r\n', eegDeviceName);
    
    % Query number of channels
    pnet(con, 'printf', 'DEVICE PARAM GET nchannels\r\n');
    tokens = tokenize_message(con);
    eegDeviceNchannels = tokens{5};
    if isempty( eegTargetChannelListString ) || strcmpi( strtrim( eegTargetChannelListString ), 'all' ) || ( strcmp(eegTargetChannelListString, '0') ), %#ok<STCMP>
        eegTargetChannelListString = compactString( sprintf( '%d ', 0:eegDeviceNchannels-1 ) );
    end
    
    pnet(con, 'printf', 'DEVICE PARAM SET target_channels %s\r\n', eegTargetChannelListString);
    pnet(con, 'printf', 'CLASSIFIER SET ssvep\r\n');
    pnet(con, 'printf', 'CLASSIFIER PARAM SET cl_type %s\r\n', classifier);
    pnet(con, 'printf', 'CLASSIFIER PARAM SET window_size %f\r\n', ssvepWindowSize);
    pnet(con, 'printf', 'CLASSIFIER PARAM SET window_step %f\r\n', reclassificationInterval);
    pnet(con, 'printf', 'DEVICE PARAM SET buffer_size_seconds %f\r\n', reclassificationInterval);
    pnet(con, 'printf', 'CLASSIFIER PARAM SET bandpass 3 45\r\n');
    pnet(con, 'printf', 'CLASSIFIER PARAM SET nharmonics %d\r\n', nHarmonics);
    
    % TODO: find a nice one liner to do this...
    frequencyListString = '';
    for f = frequencyList
        frequencyListString = [frequencyListString, ' ', num2str(f)];
    end
    pnet(con, 'printf', 'CLASSIFIER PARAM SET freqs %s\r\n', frequencyListString);
    
    % Open device and initialize the classifier (no actual training data needed)
    pnet(con, 'printf', 'DEVICE OPEN\r\n');
    wait_for_message(con, 'MODE PROVIDE "idle"');
    
    pnet(con, 'printf', 'MODE SET training\r\n');
    wait_for_message(con, 'MODE PROVIDE "training"');
    % Training...
    wait_for_message(con, 'MODE PROVIDE "idle"'); % done!
    
    logThis( 'experiment tag:      %s', tagExperiment );
    logThis( 'host name:           %s', hostName );
    if saveLog,
        logThis( 'client log filename: %s', logFilename );
    end
    logThis( 'arrows on periphery: %g', arrowsOnPeriphery );
    logThis( 'avatar is moving:    %g', avatarCanMove );
    
    %-------------------------------------------------------------------------
    % init graphics
    
    try
        Screen( 'Preference', 'Verbosity', 2 );
        %         Screen( 'Preference', 'SkipSyncTests', 0 );
        if ~isempty( nFramesForPTBtest ) && nFramesForPTBtest > 0,
            Screen( 'Preference', 'SkipSyncTests', 0 );
        else
            Screen( 'Preference', 'SkipSyncTests', 1 );
        end
        screenList = Screen( 'Screens' );
        try
            if numel( screenList ) == 1,
                if debugMode,
                    [iPTBwindow, windowPosition] = Screen( 'OpenWindow', 0, 0, [620 10 1900 1034] );
                else
                    [iPTBwindow, windowPosition] = Screen( 'OpenWindow', 0, 0 );
                end
            else
                %         [iPTBwindow, windowPosition] = Screen( 'OpenWindow', 1, 0 );
                [iPTBwindow, windowPosition] = Screen( 'OpenWindow', max( screenList ), 0 );
            end
        catch%#ok<*CTCH>
            logThis( 'Failed to initialize PTB graphics. Trying to skip sync tests...' );
            Screen( 'Preference', 'SkipSyncTests', 1 );
            if numel( screenList ) == 1,
                if debugMode,
                    [iPTBwindow, windowPosition] = Screen( 'OpenWindow', 0, 0, [620 10 1900 1034] );
                else
                    [iPTBwindow, windowPosition] = Screen( 'OpenWindow', 0, 0 );
                end
            else
                %         [iPTBwindow, windowPosition] = Screen( 'OpenWindow', 1, 0 );
                [iPTBwindow, windowPosition] = Screen( 'OpenWindow', max( screenList ), 0 );
            end
        end
        
        HideCursor();
        Screen( 'BlendFunction', iPTBwindow, GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA );
        scrFlipInterval = Screen( 'GetFlipInterval', iPTBwindow, nFramesForPTBtest );
        scrFPS = 1 / scrFlipInterval;
        nScrCols = windowPosition(3);
        nScrRows = windowPosition(4);
        logThis( 'PTB graphics is initialized' )
    catch%#ok<*CTCH>
        Screen( 'CloseAll' );
        logThis( 'Failed to initialize PTB graphics. Exiting' )
        psychrethrow( psychlasterror );
        return
    end
    
    if initialAvatarSize<=0,
        initialAvatarSize = round( 160 * min( nScrCols/1920, nScrRows/1200 ) );
    end
    
    if stimulusSize<=0
        stimulusSize = round( 350 * min( nScrCols/1920, nScrRows/1200 ) );
    end
    
    nFramesPerCell = round( scrFPS / avatarSpeed );   % number of frames needed for one move
    
    if ~exist( 'stimulusSize', 'var' ) || isempty(stimulusSize),
        stimulusSize = ceil( .2*min(nScrCols, nScrRows) );
    end
    
    logThis( 'Graphics stats: flip-interval:%-8.6f ms   frame-rate:%-8.5f Hz', ...
        scrFlipInterval, scrFPS);
    logThis( 'Screen size:          %g x %g px', nScrCols, nScrRows );
    logThis( 'Stimulus size:        %g px', stimulusSize );
    
    
    mazeMaxWidth  = nScrCols - 2*stimulusSize(1);
    mazeMaxHeight = nScrRows - 2*stimulusSize(end);
    
    
    
    KbName( 'UnifyKeyNames' );
    
    rightKey                = KbName( 'rightArrow' );
    leftKey                 = KbName( 'leftArrow' );
    upKey                   = KbName( 'upArrow' );
    downKey                 = KbName( 'downArrow' );
    stayKey                 = KbName( 'return');
    exitKey                 = KbName( 'escape' );
    screenshotKey           = KbName( 'p' );
    pauseKey                = KbName( 'space' );
    
    logThis( 'Stimulus frequency list: [%7.4f %7.4f %7.4f %7.4f] Hz', frequencyList );
    
    
    
    logThis( 'Loading and processing images' );
    avatarImg               = loadTexture( 'textures/avatar.png' );
    exitImg                 = loadTexture( 'textures/exit-marker.png' );
    arrowLeftImg            = loadTexture( 'textures/arrow-left-active.png' );
    arrowUpImg              = loadTexture( 'textures/arrow-up-active.png' );
    arrowRightImg           = loadTexture( 'textures/arrow-right-active.png' );
    arrowDownImg            = loadTexture( 'textures/arrow-down-active.png' );
    decisionCellMarkerImg   = loadTexture( 'textures/decision-cell-marker.png' );
    noDecisionMarkerImg     = loadTexture( 'textures/no-decision-marker.png' );
    specialCellMarkerImg    = loadTexture( 'textures/special-cell-marker.png' );
    
    logThis( 'Loading textures into texture memory' )
    arrowTex(1) = Screen( 'MakeTexture', iPTBwindow, arrowLeftImg );
    arrowTex(2) = Screen( 'MakeTexture', iPTBwindow, arrowUpImg );
    arrowTex(3) = Screen( 'MakeTexture', iPTBwindow, arrowRightImg );
    arrowTex(4) = Screen( 'MakeTexture', iPTBwindow, arrowDownImg );
    arrowTex(5) = Screen( 'MakeTexture', iPTBwindow, noDecisionMarkerImg );
    avatarTex   = Screen( 'MakeTexture', iPTBwindow, avatarImg );
    
    
%     if showBands,
%         alphaBandTex = Screen( 'MakeTexture', iPTBwindow, reshape( [255 0   0   255], [1 1 4] ) );
%         deltaBandTex = Screen( 'MakeTexture', iPTBwindow, reshape( [0   255 0   255], [1 1 4] ) );
%         thetaBandTex = Screen( 'MakeTexture', iPTBwindow, reshape( [0   0   255 255], [1 1 4] ) );
%         alphaTex     = Screen( 'MakeTexture', iPTBwindow, alphaImg );
%         deltaTex     = Screen( 'MakeTexture', iPTBwindow, deltaImg );
%         thetaTex     = Screen( 'MakeTexture', iPTBwindow, thetaImg );
%     end
    continueToPlay = true;
    iLevel = 1;
    
    

    
    
    while continueToPlay,
        pnet(con, 'printf', 'MODE SET "application"\r\n');
        wait_for_message(con, 'MODE PROVIDE "application"');
        
        clear mazeData mazeImg
        nDecisions = 0;
        nCorrectDecisions = 0;
        if experimentMode,
            mazeData = generateMaze( 'testLevel' ); % 'spiral-6x6-ccw'
        else
            avatarSize      = floor( initialAvatarSize * 0.9^(iLevel-1) );
            avatarOffset    = floor( avatarSize/15 );
            avatarStep      = avatarSize + 2*avatarOffset;
            mazeData        = generateRandomMaze( ...
                floor( mazeMaxWidth/avatarStep ), ... number of columns
                floor( mazeMaxHeight/avatarStep ) ... number of nRows
                );
        end
        avatarSize  = floor( 0.85 * min( mazeMaxWidth/mazeData.C, mazeMaxHeight/mazeData.R ) );
        avatarOffset= floor( avatarSize/15 );
        avatarStep  = avatarSize + 2*avatarOffset;
        
        if godMode,
            mazeData.adjacent = ones( size( mazeData.adjacent ) );
        end
        
        if ~all( isfield( mazeData, {'startRow', 'startCol', 'exitRow', 'exitCol' }) ),
            if experimentMode,
                mazeData.startRow  = ceil( mazeData.R/2 );
                mazeData.startCol  = ceil( mazeData.C/2 );
            else
                mazeData.startRow  = 1;
                mazeData.startCol  = 1;
            end
            mazeData.exitRow   = mazeData.R;
            mazeData.exitCol   = mazeData.C;
        end
        
        if treatAllCellsAsDecisionCells,
            mazeData.cellLabels = ones( mazeData.R*mazeData.C, 1 );
        else
            if ~isfield( mazeData, 'cellLabels' ),
                mazeData = labelMaze( mazeData );
            end
        end
        
        
        decisionCellIndices = find( mazeData.cellLabels == decisionCellLabel );
        nDecisionCells = numel( decisionCellIndices );
        
        mazeData.cellLabels((mazeData.exitCol-1)*mazeData.R + mazeData.exitRow) = exitCellLabel;
        
        iStartCell = find( mazeData.cellLabels == startCellLabel );
        iFinishCell = find( mazeData.cellLabels == exitCellLabel );
        
        correctMovesAvailable = isfield( mazeData, 'correctMoves' ) && ( numel( mazeData.correctMoves ) == mazeData.R * mazeData.C );
        
        
        mazeImg = generateMazeMask( mazeData, avatarStep, avatarOffset, 120, 0 );
        mazeImg = repmat( mazeImg, [1 1 3] );
        
        bgPatch = double( mazeImg(  (mazeData.exitRow-1)*avatarStep(1) + avatarOffset + (1:avatarSize(1)), ...
            (mazeData.exitCol-1)*avatarStep(end) + avatarOffset + (1:avatarSize(end)), :) );
        
        
        if arrowsOnPeriphery,
            arrowPositions = [  1           (nScrRows-stimulusSize)/2   stimulusSize                (nScrRows+stimulusSize)/2      % Left arrow
                (nScrCols-stimulusSize)/2   1                           (nScrCols+stimulusSize)/2   stimulusSize                   % Up arrow
                nScrCols-stimulusSize+1     (nScrRows-stimulusSize)/2   nScrCols                    (nScrRows+stimulusSize)/2      % Right arrow
                (nScrCols-stimulusSize)/2   nScrRows-stimulusSize       (nScrCols+stimulusSize)/2   nScrRows];                      % Down arrow
        else
            arrowPositions = [  -stimulusSize  -(stimulusSize-avatarSize)/2    -1                              +(stimulusSize+avatarSize)/2
                -(stimulusSize-avatarSize)/2    -stimulusSize                   +(stimulusSize+avatarSize)/2    -1
                +avatarSize                     -(stimulusSize-avatarSize)/2    +stimulusSize+avatarSize        +(stimulusSize+avatarSize)/2
                -(stimulusSize-avatarSize)/2     +avatarSize                    +(stimulusSize+avatarSize)/2    +stimulusSize+avatarSize];
        end
        
        mazeULcornerCoords = [ round((nScrCols-size(mazeImg, 2))/2) round((nScrRows-size(mazeImg, 1))/2)];
        mazePosition = [ mazeULcornerCoords (mazeULcornerCoords+[size(mazeImg, 2) size(mazeImg, 1)]-1)];
        
        
        avatarPosition = mazeULcornerCoords + avatarStep.*[mazeData.startCol-1 mazeData.startRow-1] + avatarOffset;
        avatarPosition = [ avatarPosition avatarPosition+avatarSize-1]; %#ok<AGROW>

        
        if experimentMode && correctMovesAvailable,
            winnerCommandChar = upper( mazeData.correctMoves((mazeData.startCol-1)*mazeData.R + mazeData.startRow) );
            iWinnerCommand = find( commandList == winnerCommandChar, 1, 'first' );
            commandQueue = iWinnerCommand( ones( 1, queueSize ) );
            commandVotes = zeros( nCommands, 1);
            commandVotes(iWinnerCommand) = queueSize;
        else
            commandQueue = iCommandStay( ones( 1, queueSize ) );
            commandVotes = zeros( nCommands, 1);
            commandVotes(iCommandStay) = queueSize;
            iWinnerCommand = iCommandStay;
            winnerCommandChar = commandList(iWinnerCommand);
        end
        
        
        if showQueue,
            queueSymbolSize = round( (nScrCols-stimulusSize)*.2 / queueSize );
            queueLeftMargin = nScrCols - queueSymbolSize*queueSize;
            queuePositions = zeros( queueSize, 4 );
            queuePositionShift = 0;
            queuePositionShiftInc = queueSymbolSize / ( scrFPS * reclassificationInterval );
            queuePositions(:,1) = queueLeftMargin:queueSymbolSize:nScrCols-1;
            queuePositions(:,2) = 1;
            queuePositions(:,3) = queuePositions(:,1) + queueSymbolSize - 1;
            queuePositions(:,4) = queueSymbolSize;
            queueAlphas = queueWeightList;
        else
            queuePositions = [];
            queueAlphas = [];
        end
        
        if showDecision,
            decisionSymbolSize = round( (nScrCols-stimulusSize)*.5 / queueSize );
            decisionSymbolPosition = [nScrCols-decisionSymbolSize+1 1 nScrCols decisionSymbolSize];
            if showQueue,
                decisionSymbolPosition = decisionSymbolPosition + [0 queueSymbolSize+1 0 queueSymbolSize+1];
            end
            decisionSymbolAlpha = 1;
        else
            decisionSymbolPosition      = [];
            decisionSymbolAlpha         = [];
        end
        
        % decision cell markers
        if markDecisionCells,
            logThis( 'Marking decision cells' )
            decisionCellPatch = blendIn( decisionCellMarkerImg, bgPatch );
            % blend special cell markers in to maze texture
            for iDC = 1:nDecisionCells,
                cellCol = floor( (decisionCellIndices(iDC)-1) / mazeData.R ) + 1;
                cellRow = decisionCellIndices(iDC) - (cellCol-1)*mazeData.R;
                
                locPatch = mazeImg( (cellRow-1)*avatarStep(1) + avatarOffset + (1:avatarSize(1)), ...
                    (cellCol-1)*avatarStep(end)+ avatarOffset + (1:avatarSize(end)), :);
                decisionCellPatch = blendIn( decisionCellMarkerImg, locPatch );
                
                mazeImg( (cellRow-1)*avatarStep(1) + avatarOffset + (1:avatarSize(1)), ...
                    (cellCol-1)*avatarStep(end)+ avatarOffset + (1:avatarSize(end)), :) = uint8( decisionCellPatch );
            end % of special cell loop
        end % of mark decision cells branch
        
        % special cell markers
        if markSpecialCells,
            logThis( 'Marking special cells' )
            specialCellIndices = find( mazeData.cellLabels == specialCellLabel );
            nSpecialCells = numel( specialCellIndices );
            % blend special cell markers in to maze texture
            for iSC = 1:nSpecialCells,
                cellCol = floor( (specialCellIndices(iSC)-1) / mazeData.R ) + 1;
                cellRow = specialCellIndices(iSC) - (cellCol-1)*mazeData.R;
                
                locPatch = mazeImg( (cellRow-1)*avatarStep(1) + avatarOffset + (1:avatarSize(1)), ...
                    (cellCol-1)*avatarStep(end)+ avatarOffset + (1:avatarSize(end)), :);
                specialCellPatch = blendIn( specialCellMarkerImg, locPatch );
                
                mazeImg( (cellRow-1)*avatarStep(1) + avatarOffset + (1:avatarSize(1)), ...
                    (cellCol-1)*avatarStep(end)+ avatarOffset + (1:avatarSize(end)), :) = uint8( specialCellPatch );
            end % of special cell loop
        end % of mark special cells branch
        
        % correct decision markers
        if correctMovesAvailable && markCorrectDecisions,
            logThis( 'Marking correct moves' )

            % blend special cell markers in to maze texture
            for iDC = 1:nDecisionCells,
                cellCol = floor( (decisionCellIndices(iDC)-1) / mazeData.R ) + 1;
                cellRow = decisionCellIndices(iDC) - (cellCol-1)*mazeData.R;
                
                locPatch = mazeImg( (cellRow-1)*avatarStep(1) + avatarOffset + (1:avatarSize(1)), ...
                    (cellCol-1)*avatarStep(end)+ avatarOffset + (1:avatarSize(end)), :);
                
                arrowImg = [];
                switch upper( mazeData.correctMoves(decisionCellIndices(iDC)) ),
                    case commandGoLeftChar,    arrowImg = arrowLeftImg;
                    case commandGoRightChar,   arrowImg = arrowRightImg;
                    case commandGoUpChar,      arrowImg = arrowUpImg;
                    case commandGoDownChar,    arrowImg = arrowDownImg;
                end
                if ~isempty( arrowImg ),
                    decisionCellPatch = blendIn( arrowImg, locPatch, .3 );
                    mazeImg( (cellRow-1)*avatarStep(1) + avatarOffset + (1:avatarSize(1)), ...
                        (cellCol-1)*avatarStep(end)+ avatarOffset + (1:avatarSize(end)), :) = uint8( decisionCellPatch );
                end
            end % of loop over decision cells
            
        end % of mark correct decision cells branch
        
        
        % exit marker
        exitPatch = blendIn( exitImg, bgPatch );
        mazeImg( (mazeData.exitRow-1)*avatarStep(1) + avatarOffset + (1:avatarSize(1)), ...
            (mazeData.exitCol-1)*avatarStep(end)+ avatarOffset + (1:avatarSize(end)), :) = uint8( exitPatch );
        
        clear mazeTex
        mazeTex = Screen( 'MakeTexture', iPTBwindow, mazeImg );
        
        Screen( 'BlendFunction', iPTBwindow, GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA );
        
        textureList     = [mazeTex arrowTex(1:4) avatarTex];
        if showQueue,
            textureList = [textureList repmat( arrowTex(5), [1 queueSize] ) ]; %#ok<AGROW>
        end
        if showDecision,
            textureList = [textureList arrowTex(5) ]; %#ok<AGROW>
            decisionSymbolTextureIndex = numel( textureList );
        end
        
        textureAlphas       = [ ones( 1, 6 ) queueAlphas decisionSymbolAlpha];
        texturePositions    = [mazePosition' arrowPositions' avatarPosition' queuePositions' decisionSymbolPosition'];
        
        
        iFrame = 0;
        HideCursor
        levelAccomplished = 0;
        
        currentAvatarPosition   = [mazeData.startCol mazeData.startRow]; %avatarPosition(1:2);
        desiredAvatarPosition   = currentAvatarPosition;

        targetLocation = mazeULcornerCoords + avatarOffset;
        nFramesStillToMove = 0;
        
        nDroppedFrames              = 0;
        timeBeforeRendering         = 0;
        averageRenderingTime        = 0;
        currentFrameRenderingTime   = 0;
        avatarPosition = mazeULcornerCoords + avatarStep*(currentAvatarPosition-1) + avatarOffset;
        
        if ~experimentMode,
            Screen( 'TextFont', iPTBwindow, 'Arial' );
            Screen( 'TextSize', iPTBwindow, 80 );
            DrawFormattedText( iPTBwindow, sprintf( 'Level %g', iLevel ), 'center', 'center', [255 255 255 200]);
            Screen( 'Flip', iPTBwindow );
            pause( 1 );
        end
        
        Priority( 1 );
        
        [~, ~, lastFlipTime] = Screen( 'Flip', iPTBwindow, 0, 1 );
        [~, ~, lastFlipTime] = Screen( 'Flip', iPTBwindow, 0, 1 );
        nextFlipTime = lastFlipTime + scrFlipInterval;
        
        exitKeyPressed = false;
        commandArrived   = false;

        logThis( 'Entering the main loop' )
        
        iCurrentCell = (currentAvatarPosition(1)-1)*mazeData.R + currentAvatarPosition(2);
        iTargetCell = iCurrentCell;
%         assert( iCurrentCell == iStartCell, 'iCurrentCell ~= iStartCell' );
        lookForANewTarget = true;        
        while ~exitKeyPressed && ~levelAccomplished,
            
            [ keyIsDown, ~, keyCode ] = KbCheck();
            exitKeyPressed = keyIsDown && keyCode(exitKey);
            if exitKeyPressed, break, end;
            
            commandArrived = ~isempty( pnet(con, 'read', 1, 'char', 'view', 'noblock') );
            if commandArrived,
                queuePositionShift = 0;

                %pnet(con, 'readline');
                %newCommandChar = '1';
                %while true,
                    tokens = tokenize_message(con);
                    classification_results = cell2mat(tokens(3:end));
                    [~, newCommand] = max(classification_results);
                    newCommandChar = num2str(newCommand);
                 %   if isempty( newCommandChar ),
                 %       break
                 %   end
                    commandChar = newCommandChar;
                %end
                
                if keyIsDown,
                    if keyCode(leftKey)
                        commandChar = commandGoLeftChar;
                    elseif keyCode(upKey),
                        commandChar = commandGoUpChar;
                    elseif keyCode(rightKey),
                        commandChar = commandGoRightChar;
                    elseif keyCode(downKey),
                        commandChar = commandGoDownChar;
                    elseif keyCode(stayKey),
                        commandChar = commandStayChar;
                    elseif keyCode(screenshotKey),
                        logThis( 'screen shot key pressed' )
                        % snapshot
                        imwrite( Screen( 'GetImage', iPTBwindow ), sprintf( 'the-maze-game-screenshot-[%04g-%02g-%02g-%02g-%02g-%06.3f].png', clock() ) )
                    elseif keyCode(pauseKey),
                        % pause
                        logThis( 'pause key pressed' )
                    end
                end % of command from keyboard/server branches
                
                iEnteringCommand = iCommandStay;
                if commandChar,
                    iEnteringCommand = find( commandList == commandChar );
                    if isempty( iEnteringCommand ),
                        iEnteringCommand = iCommandStay;
                    end
                end

                % new strategy all commands in the queue are NOT equal
                commandQueue = [iEnteringCommand commandQueue(1:queueSize-1)];
                
                if showOnlyPossibleMoves || useOnlyPossibleMoves,
                    possibleMoveMasks = mazeData.adjacent(iTargetCell,[4 1 2 3]);
                end
                
                commandVotes = zeros( nCommands, 1 );
                for iQ = 1:queueSize,
                    iC = commandQueue(iQ);
                    if useOnlyPossibleMoves && iC < nCommands,
                        commandVotes(iC) = commandVotes(iC) + possibleMoveMasks(iC) * queueWeightList(iQ);
                    else
                        commandVotes(iC) = commandVotes(iC) + queueWeightList(iQ);
                    end
                end % of queue loop
                
                %                 iWinnerCommand = find( commandVotes > winnerThreshold );
                [bestVote, iWinnerCommand] = max( commandVotes );
                
                if isempty( iWinnerCommand ) || numel( iWinnerCommand ) > 1 || bestVote < decisionThreshold,
                    iWinnerCommand = iCommandStay;
                end
                
                winnerCommandChar = commandList(iWinnerCommand);
                
                if showQueue,
                    textureList(6+(1:queueSize)) = arrowTex(commandQueue);
                end
                if showQueueText,
                    logThis( 'command-queue:[%s]  votes:[%s]  iWinner:%g  cWinner:%c', ...
                        sprintf( '%2g', commandQueue ), ...
                        sprintf( ' %5.2f', commandVotes), ...
                        iWinnerCommand, ...
                        winnerCommandChar );
                end
                
            end % of commandArrived condition
            
            lookForANewTarget = commandArrived && ( bestVote >= decisionThreshold ) && ( winnerCommandChar ~= commandStayChar ) ...
                && avatarCanMove && (nFramesStillToMove == 0);
            
            if avatarCanMove,
                
                if (nFramesStillToMove == 0),
                    currentAvatarPosition = desiredAvatarPosition;
                    avatarPosition = mazeULcornerCoords + avatarStep*(currentAvatarPosition-1) + avatarOffset;
                    iCurrentCell = (currentAvatarPosition(1)-1)*mazeData.R + currentAvatarPosition(2);
                    
                    levelAccomplished = (iCurrentCell == iFinishCell);
                    if levelAccomplished,
                        break
                    end
                end
                
                if lookForANewTarget,
    
                    if correctMovesAvailable, % && ( iCurrentCell ~= iPrevDecisionCell ),
                        nDecisions = nDecisions + 1;
%                         logThis( 'iCurrentCell:                         %d', iCurrentCell );
%                         logThis( 'iTargetCell:                          %d', iTargetCell );
%                         logThis( 'mazeData.correctMoves(iCurrentCell):  %c', mazeData.correctMoves(iCurrentCell) );
%                         logThis( 'mazeData.correctMoves(iTargetCell):   %c', mazeData.correctMoves(iTargetCell) );
%                         logThis( 'winnerCommandChar:                    %c', winnerCommandChar );                        
                        
                        if winnerCommandChar == mazeData.correctMoves(iCurrentCell),
%                             logThis( 'Correct decision!!!' );
                            nCorrectDecisions = nCorrectDecisions + 1;
                        else
%                             logThis( 'Wrong decision!!!' );                            
                            if disableWrongMoves,
                                iWinnerCommand = iCommandStay;
                                winnerCommandChar = commandList(iWinnerCommand);
                                lookForANewTarget = false;
                            end
                            
                            if flushDecisionQueueOnMistake,
%                                 logThis( 'Flushing the decision queue' );
                                commandQueue = iCommandStay( ones( 1, queueSize ) );
                                commandVotes = zeros( nCommands, 1);
                                commandVotes(iCommandStay) = queueSize;
                                iWinnerCommand = iCommandStay;
                                winnerCommandChar = commandList(iWinnerCommand);
                            end
                        end % of incorrect move branch
                        
                        if iCurrentCell == iStartCell,
                            nDecisions = nDecisions - 1;
                            nCorrectDecisions = nCorrectDecisions - 1;
                        elseif iCurrentCell == iFinishCell,
                            nDecisions = nDecisions - 1;
                        else
                            logThis( 'Number of decisions made: %2g  number of correct decisions: %2g', ...
                                nDecisions, nCorrectDecisions );
                        end
                        
                    end % of test for correctness of the new decision branch
                    
                    iTargetCell  = iCurrentCell;
                    nCellsToMove = 0;
                        
                    if lookForANewTarget,
                        switch winnerCommandChar,
                            case commandGoLeftChar, %'L',
                                while (mazeData.adjacent(iTargetCell,4)==1) % && (currentAvatarPosition(1)>1),
                                    desiredAvatarPosition(1) = desiredAvatarPosition(1) - 1;
                                    iTargetCell = iTargetCell - mazeData.R;
                                    nCellsToMove = nCellsToMove + 1;
                                    if mazeData.cellLabels(iTargetCell), % if target cell is not "regular" one
                                        break
                                    end
                                end % of search to the left loop
                                
                            case commandGoRightChar, %'R',
                                while (mazeData.adjacent(iTargetCell,2)==1) % && (currentAvatarPosition(1)<mazeData.C)
                                    desiredAvatarPosition(1) = desiredAvatarPosition(1) + 1;
                                    iTargetCell = iTargetCell + mazeData.R;
                                    nCellsToMove = nCellsToMove + 1;
                                    if mazeData.cellLabels(iTargetCell), % if target cell is not "regular" one
                                        break
                                    end
                                end % of search to the right loop
                                
                            case commandGoUpChar, %'U',
                                while (mazeData.adjacent(iTargetCell,1)==1) % && (currentAvatarPosition(2)>1),
                                    desiredAvatarPosition(2) = desiredAvatarPosition(2) - 1;
                                    iTargetCell = iTargetCell - 1;
                                    nCellsToMove = nCellsToMove + 1;
                                    if mazeData.cellLabels(iTargetCell), % if target cell is not "regular" one
                                        break
                                    end
                                end % of up-search  loop
                                
                            case commandGoDownChar, %'D',
                                while (mazeData.adjacent(iTargetCell,3)==1) % && (currentAvatarPosition(2)<mazeData.R),
                                    desiredAvatarPosition(2) = desiredAvatarPosition(2) + 1;
                                    iTargetCell = iTargetCell + 1;
                                    nCellsToMove = nCellsToMove + 1;
                                    if mazeData.cellLabels(iTargetCell), % if target cell is not "regular" one
                                        break
                                    end
                                end % of down-search  loop
                                
                        end % of winnerCommandChar switch

                    end % of lookForANewTarget branch

                    %                 nFramesStillToMove = nFramesPerCell;
                    nFramesToMove       = nFramesPerCell * nCellsToMove;
                    nFramesStillToMove  = nFramesToMove;
                    targetLocation      = mazeULcornerCoords + avatarOffset + avatarStep .* (desiredAvatarPosition-.5);
                    
                end % if nFramesStillToMove == 0
                
                
                if nFramesStillToMove > 0,
                    k = nFramesStillToMove / nFramesToMove;
                    avatarPosition = mazeULcornerCoords + avatarOffset + ...
                        avatarStep .* ((currentAvatarPosition-1)*k + (desiredAvatarPosition-1)*(1-k));
                    nFramesStillToMove = nFramesStillToMove - 1;
                end
            else
                % avatarPosition = round( mazeULcornerCoords + avatarOffset + avatarStep .* (currentAvatarPosition-1) ); %#ok<*UNRCH>
                avatarPosition = mazeULcornerCoords + avatarOffset + avatarStep .* (currentAvatarPosition-1); %#ok<*UNRCH>
            end % of moving avatar condition
            
            iCurrentCell = (currentAvatarPosition(1)-1)*mazeData.R + currentAvatarPosition(2);
            
            if arrowsOnPeriphery,
                arrowRectangles = arrowPositions;
            else
                arrowRectangles = arrowPositions + repmat( avatarPosition(1:2), [4 2] );
                texturePositions(:,2:5) = arrowRectangles';
            end
            
            avatarPosition(3:4) = avatarPosition(1:2) + round( avatarSize );
            texturePositions(:,6) = avatarPosition';
            
            if showQueue,
                texturePositions([1 3],6+(1:queueSize)) = queuePositions(:,[1 3])' + queuePositionShift;
                if queuePositionShift < queueSymbolSize,
                    queuePositionShift = queuePositionShift + queuePositionShiftInc;
                end
            end
            
            if showDecision,
                textureList(decisionSymbolTextureIndex) = arrowTex(iWinnerCommand);
            end
            
            timeBeforeRendering = GetSecs();
            if timeBeforeRendering + averageRenderingTime > nextFlipTime,
                nDroppedFrames = ceil( (timeBeforeRendering + averageRenderingTime - nextFlipTime)/scrFlipInterval );
                nextFlipTime = nextFlipTime + scrFlipInterval * nDroppedFrames;
                logThis( 'Dropped frames: %g', nDroppedFrames );
            end
            
            phases = 2*pi * nextFlipTime * frequencyList;
            
            if showOnlyPossibleMoves,
                textureAlphas(2:5) = possibleMoveIntensities(1+possibleMoveMasks) .* ( 1 + sin(phases) ) / 2;
            else
                textureAlphas(2:5) = ( 1 + sin(phases) ) / 2;
            end
            
            if useOnOffStimulation,
                textureAlphas(2:5) = round( textureAlphas(2:5) );
            end                
            
            Screen( ...
                'DrawTextures', ...
                iPTBwindow, ...         windowPointer
                textureList, ...        texturePointer
                [], ...                 sourceRect
                texturePositions, ...   destinationRect
                0, ...                  rotationAngle
                0, ...                  filterMode
                textureAlphas ...       globalAlpha
                );
            
            currentFrameRenderingTime = GetSecs() - timeBeforeRendering;
            
            [~, ~, lastFlipTime] = Screen( 'Flip', iPTBwindow );
            nextFlipTime = lastFlipTime + scrFlipInterval;
            averageRenderingTime =  ( averageRenderingTime*iFrame + currentFrameRenderingTime ) / (iFrame+1) ;
            iFrame = iFrame + 1;
            
%             levelAccomplished = (currentAvatarPosition(1) == mazeData.exitCol) && (currentAvatarPosition(2) == mazeData.exitRow);

            if gameStartTime == 0,
                gameStartTime = lastFlipTime;
            end
            
        end % of main loop

        logThis( 'Stopping the BCI server.' );
        pnet(con, 'printf', 'MODE SET idle\r\n');
        wait_for_message(con, 'MODE PROVIDE "idle"', 1);

        gameStopTime = lastFlipTime;
        
        Priority( 0 );
        if experimentMode,
            continueToPlay = false;
            Screen( 'TextFont', iPTBwindow, 'Arial' );
            Screen( 'TextSize', iPTBwindow, 80 );
            DrawFormattedText( iPTBwindow, 'Thank you!', 'center', 'center', [255 255 0 200] );
            Screen( 'Flip', iPTBwindow );
            flushKeyboardQueue();
            break
        else
            if levelAccomplished,
                iLevel = iLevel + 1;
                Screen( 'TextFont', iPTBwindow, 'Arial' );
                Screen( 'TextSize', iPTBwindow, 70 );
                %     Screen( 'DrawText', iPTBwindow, 'Congratulations!', 'center' 500, 500, [255 0  0 200]);
                DrawFormattedText( iPTBwindow, 'Congratulations!', 'center', 'center', [255 255 0 200] );
                Screen( 'Flip', iPTBwindow );
                flushKeyboardQueue();
                Screen( 'Flip', iPTBwindow, [], 0 );
            else
                continueToPlay = false;
                Screen( 'TextFont', iPTBwindow, 'Arial' );
                Screen( 'TextSize', iPTBwindow, 80 );
                DrawFormattedText( iPTBwindow, 'Game Over!', 'center', 'center', [255 0 0 200] );
                Screen( 'Flip', iPTBwindow );
                flushKeyboardQueue();
            end % of levelAccomplished condition
        end
        
    end % of continueToPlay loop
      
    logThis( 'Disconnecting from the BCI server.' );
    pnet(con, 'close');
     
    %% Finish
    
    logThis( 'Finishing and cleaning up' );
    % Done. Close Screen, release all resources:
    Screen( 'CloseAll' );
    if experimentMode,
        subjectiveControlLevel = controlLevelValidationGUI();
        logThis( 'Number of decisions made:             %g', nDecisions );
        logThis( 'Number number of correct decisions:   %g', nCorrectDecisions );
        logThis( 'Accuracy:                             %6.2f%%', 100*nCorrectDecisions/nDecisions );
        logThis( 'Experimental level play duration:     %7.3f seconds', gameStopTime - gameStartTime );
        logThis( 'User game control subjective level:   %6.2f%%', 100*subjectiveControlLevel );
        if updateReport,
            reportFilename = 'The-Maze-game-report.txt';
            if exist( './reports', 'dir' ),
                reportFilename = [ './reports/' reportFilename];
            end
            logThis( [], 'logFilename', reportFilename );
            logThis( '%-20s\t%-16s\t[%5.2f %5.2f %5.2f %5.2f]\t%d\t%5.2f\t%5.2f\t%5.2f\t%d\t%d\t%d\t%6.2f%%\t%7.3f\t%6.2f%%', ...
                subjectTag, ...
                eegDeviceName, ...
                frequencyList, ...
                nHarmonics, ...
                ssvepWindowSize, ...
                avatarSpeed, ...
                1/reclassificationInterval, ...
                queueSize, ...
                nDecisions, nCorrectDecisions, 100*nCorrectDecisions/nDecisions, ...
                gameStopTime - gameStartTime, ...
                100*subjectiveControlLevel ...
                );
            logThis( [], 'logFilename', '', 'logToFile', false );
        end
    end
 
end % of MAZECLIENT() function

%--------------------------------------------------------------------------
function flushKeyboardQueue()
    for i = 1:50,
        if KbCheck(),
            break
        end
        pause( .1 );
    end
end % of FLUSHKEYBOARDQUEUE() function

%--------------------------------------------------------------------------
function textureData = loadTexture( textureFilename, textureSize )
    
    [textureData, ~, alphaChannel] = imread( textureFilename );
    
    if (nargin < 2) || isempty( textureSize ),
        textureSize = [size( textureData, 1 ) size( textureData, 2 )];
    else
        if numel( textureSize ) == 1,
            textureSize(2) = textureSize(1);
        end
    end
    textureSize = textureSize(1:2);
    
    if isempty( alphaChannel ),
        alphaChannel = 255;
    end
    
    if ( textureSize(1) ~= size( textureData, 1 ) ) || ( textureSize(2) ~= size( textureData, 2 ) ),
        textureData  = imresize( textureData, textureSize );
        alphaChannel = imresize( alphaChannel, textureSize );
    end
    
    textureData(:,:,end+1) = alphaChannel;
    
end % of LOADTEXTURE() function

%--------------------------------------------------------------------------------------------
function mi = generateMazeMask( maze, cellSize, wallWidth, wallValue, backgroundValue )
    if nargin<2, cellSize  = 6; end
    if nargin<3, wallWidth = ceil( cellSize/8 ); end
    if nargin<4, wallValue = 1; end
    if nargin<5, backgroundValue = 0; end
    % determine the size of the maze and set the figure accordingly
    nRows = maze.R;
    nCols = maze.C;
    
    mi = backgroundValue + zeros( nRows*cellSize+wallWidth, nCols*cellSize+wallWidth );
    wallLength     = cellSize + wallWidth;
    wallHalfWidth = ceil( wallWidth/2 );
    wallShortInd  = (1:wallWidth)  - wallHalfWidth;
    wallLongSnd   = (1:wallLength) - wallHalfWidth;
    % draw the grid
    ind = 1;
    for c = 1:nCols,
        for r = 1:nRows,
            cellULrowInd = wallHalfWidth + (r-1)*cellSize(1);
            cellULcolInd = wallHalfWidth + (c-1)*cellSize(end);
            
            % Draw the northern border
            if (maze.adjacent(ind,1) ~= 1),
                mi(cellULrowInd + wallShortInd, cellULcolInd + wallLongSnd) = wallValue;
            end
            
            % Draw the southern border
            if (maze.adjacent(ind,3) ~= 1),
                mi(cellULrowInd + cellSize(1) + wallShortInd, cellULcolInd + wallLongSnd) = wallValue;
            end
            
            % Draw the eastern border
            if (maze.adjacent(ind,2) ~= 1)
                mi(cellULrowInd + wallLongSnd, cellULcolInd + cellSize(end) + wallShortInd) = wallValue;
            end
            
            % Draw the western border
            if (maze.adjacent(ind,4) ~= 1)
                mi(cellULrowInd + wallLongSnd, cellULcolInd + wallShortInd) = wallValue;
            end
            
            ind = ind + 1;
        end % of loop over rows
    end % of loop over columns
    
end % of function GENERATEMAZEMASK()

%--------------------------------------------------------------------------------------------
function maze = generateRandomMaze( nCols, nRows )
    % based on the code BnRows JeremnRows Kubica
    
    % create the maze
    maze = struct( 'adjacent', zeros(nRows*nCols,4), 'R', nRows, 'C', nCols );
    
    % allocate space for a collection of sets
    sets = 1:(nCols*nRows);
    
    % while there are disjoint sets left...
    while( max(sets) > 1)
        
        % find out how mannRows sets are left
        L = max(sets);
        
        % pick a set and a cell from it
        set_ind = floor( rand * L ) + 1;
        set = find( sets == set_ind );
        cell_ind = floor( rand * length(set) ) + 1;
        cell = set(cell_ind);
        
        % find the coordinates of the cell
        cnCols = ceil( cell / nRows );
        cnRows = mod( cell, nRows );
        if(cnRows == 0)
            cnRows = nRows;
        end
        
        % pick a random direction to trnRows merging
        dir = floor(rand(1,1) * 4.0) + 1;
        cellNeighbor = 0;
        
        switch floor(dir)
            case 1
                cellNeighbor = cell - 1;
                nnRows = cnRows - 1;
                nnCols = cnCols;
            case 2
                cellNeighbor = cell + nRows;
                nnRows = cnRows;
                nnCols = cnCols + 1;
            case 3
                cellNeighbor = cell + 1;
                nnRows = cnRows + 1;
                nnCols = cnCols;
            case 4
                cellNeighbor = cell - nRows;
                nnRows = cnRows;
                nnCols = cnCols - 1;
        end
        
        % if a valid neighbor was found... find out which
        % set it is currentlnRows in.
        neigh_set = set_ind;
        if((nnCols <= nCols) && (nnCols > 0) && (nnRows <= nRows) && (nnRows > 0))
            neigh_set = sets(cellNeighbor);
        end
        
        % If the two sets are different merge
        if(neigh_set ~= set_ind)
            
            % merge the sets
            inds = find(sets == neigh_set);
            sets(inds) = set_ind * ones(1,length(inds));
            
            % shift evernRowsthing down 1
            inds = find(sets >= neigh_set);
            sets(inds) = sets(inds) - 1;
            
            % open the "wall" in the maze
            switch floor(dir)
                case 1
                    maze.adjacent(cell,1) = 1;
                    maze.adjacent(cellNeighbor,3) = 1;
                case 2
                    maze.adjacent(cell,2) = 1;
                    maze.adjacent(cellNeighbor,4) = 1;
                case 3
                    maze.adjacent(cell,3) = 1;
                    maze.adjacent(cellNeighbor,1) = 1;
                case 4
                    maze.adjacent(cell,4) = 1;
                    maze.adjacent(cellNeighbor,2) = 1;
            end
        end
    end
end % of GENERATERANDOMMAZE() function

%--------------------------------------------------------------------------------------------
function maze = generateMaze( mazeType )
    if ~exist( 'mazeType', 'var' ) || isempty( mazeType ),
        mazeType = 'testLevel';
    end
    switch mazeType,
        case 'testLevel',
            maze.R            = 14;
            maze.C            = 23;
            maze.startRow     = 7;
            maze.startCol     = 2;
            maze.exitRow      = 8;
            maze.exitCol      = 2;
            maze.correctMoves = 'SRSSSSSSSSSSRSDRUUUUUSUUUUUUSRSSSSSSSSSSLSSRSSSSSSSSSSLSSRSSSRSSRSSSLSDDDDDRUDDDDDLUSLSSSRSSLSSSLSSSSSSRSSLSSSSSSRSSSRSSLSSSRSDRUUUUUDLUUUUUSRSSSLSSLSSSLSSRSSSSSSSSSSLSSRSSSRSSRSSSLSDDDDDRUDDDDDLUSLSSSRSSLSSSLSSSSSSRSSLSSSSSSRSSSRSSLSSSRSDRUUUUUDLUUUUUSRSSSLSSLSSSLSSRSSSSSSSSSSLSSRSSSSSSSSSSLSDDDDDDDDDDDDLUSLSSSSSSSSSSLS';
            maze.cellLabels   = [0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 1 0 0 0 0 -1 -2 0 0 0 0 1 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 1 0 0 0 1 0 0 1 0 0 0 1 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 1 0 0 0 1 0 0 1 0 0 0 1 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 1 0 0 0 1 0 0 1 0 0 0 1 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 1 0 0 0 1 0 0 1 0 0 0 1 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 1 0 0 0 0 0 0 0 0 0 0 1 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0];
            maze.adjacent     = [1 0 0 1; 0 1 0 0; 0 0 1 1; 1 0 1 1; 1 0 1 1; 1 0 1 1; 1 0 1 1; 1 0 1 1; 1 0 1 1; 1 0 1 1; 1 0 1 1; 1 0 0 1; 0 1 0 0; 0 0 1 1; 0 0 1 0; 1 1 1 1; 1 0 1 0; 1 0 1 0; 1 0 1 0; 1 0 1 0; 1 0 0 0; 0 0 1 0; 1 0 1 0; 1 0 1 0; 1 0 1 0; 1 0 1 0; 1 1 1 1; 1 0 0 0; 1 1 0 0; 0 1 0 1; 0 1 1 0; 1 1 1 0; 1 1 1 0; 1 1 1 0; 1 1 1 0; 1 1 1 0; 1 1 1 0; 1 1 1 0; 1 1 1 0; 1 1 0 0; 0 1 0 1; 0 1 1 0; 1 1 0 1; 0 1 0 1; 0 1 1 1; 1 1 1 1; 1 1 1 1; 1 0 1 1; 1 1 1 1; 1 1 1 1; 1 0 1 1; 1 1 1 1; 1 1 1 1; 1 1 0 1; 0 1 0 1; 0 1 1 1; 1 0 0 1; 0 1 0 1; 0 0 1 1; 1 0 1 1; 1 0 0 1; 0 1 0 0; 0 0 1 1; 1 0 0 1; 0 1 0 0; 0 0 1 1; 1 0 1 1; 1 0 0 1; 0 1 0 1; 0 0 1 1; 0 0 1 0; 1 1 1 1; 1 0 1 0; 1 0 1 0; 1 0 1 0; 1 1 1 1; 1 0 0 0; 0 0 1 0; 1 1 1 1; 1 0 1 0; 1 0 1 0; 1 0 1 0; 1 1 1 1; 1 0 0 0; 1 1 0 0; 0 0 0 1; 0 1 1 0; 1 1 1 0; 1 1 0 0; 0 1 0 1; 0 1 1 0; 1 1 0 0; 0 1 0 1; 0 1 1 0; 1 1 1 0; 1 1 0 0; 0 0 0 1; 0 1 1 0; 1 1 1 1; 1 0 1 0; 1 1 1 1; 1 1 1 1; 1 1 0 1; 0 1 0 1; 0 1 1 1; 1 1 0 1; 0 1 0 1; 0 1 1 1; 1 1 1 1; 1 1 1 1; 1 0 1 0; 1 1 1 1; 1 0 0 1; 0 1 0 0; 0 0 1 1; 1 0 1 1; 1 0 0 1; 0 1 0 1; 0 0 1 1; 1 0 0 1; 0 1 0 1; 0 0 1 1; 1 0 1 1; 1 0 0 1; 0 1 0 0; 0 0 1 1; 0 0 1 0; 1 1 1 1; 1 0 1 0; 1 0 1 0; 1 0 1 0; 1 1 1 1; 1 0 0 0; 0 0 1 0; 1 1 1 1; 1 0 1 0; 1 0 1 0; 1 0 1 0; 1 1 1 1; 1 0 0 0; 1 1 0 0; 0 1 0 1; 0 1 1 0; 1 1 1 0; 1 1 0 0; 0 0 0 1; 0 1 1 0; 1 1 0 0; 0 0 0 1; 0 1 1 0; 1 1 1 0; 1 1 0 0; 0 1 0 1; 0 1 1 0; 1 1 0 1; 0 1 0 1; 0 1 1 1; 1 1 1 1; 1 1 1 1; 1 0 1 0; 1 1 1 1; 1 1 1 1; 1 0 1 0; 1 1 1 1; 1 1 1 1; 1 1 0 1; 0 1 0 1; 0 1 1 1; 1 0 0 1; 0 1 0 1; 0 0 1 1; 1 0 1 1; 1 0 0 1; 0 1 0 0; 0 0 1 1; 1 0 0 1; 0 1 0 0; 0 0 1 1; 1 0 1 1; 1 0 0 1; 0 1 0 1; 0 0 1 1; 0 0 1 0; 1 1 1 1; 1 0 1 0; 1 0 1 0; 1 0 1 0; 1 1 1 1; 1 0 0 0; 0 0 1 0; 1 1 1 1; 1 0 1 0; 1 0 1 0; 1 0 1 0; 1 1 1 1; 1 0 0 0; 1 1 0 0; 0 0 0 1; 0 1 1 0; 1 1 1 0; 1 1 0 0; 0 1 0 1; 0 1 1 0; 1 1 0 0; 0 1 0 1; 0 1 1 0; 1 1 1 0; 1 1 0 0; 0 0 0 1; 0 1 1 0; 1 1 1 1; 1 0 1 0; 1 1 1 1; 1 1 1 1; 1 1 0 1; 0 1 0 1; 0 1 1 1; 1 1 0 1; 0 1 0 1; 0 1 1 1; 1 1 1 1; 1 1 1 1; 1 0 1 0; 1 1 1 1; 1 0 0 1; 0 1 0 0; 0 0 1 1; 1 0 1 1; 1 0 0 1; 0 1 0 1; 0 0 1 1; 1 0 0 1; 0 1 0 1; 0 0 1 1; 1 0 1 1; 1 0 0 1; 0 1 0 0; 0 0 1 1; 0 0 1 0; 1 1 1 1; 1 0 1 0; 1 0 1 0; 1 0 1 0; 1 1 1 1; 1 0 0 0; 0 0 1 0; 1 1 1 1; 1 0 1 0; 1 0 1 0; 1 0 1 0; 1 1 1 1; 1 0 0 0; 1 1 0 0; 0 1 0 1; 0 1 1 0; 1 1 1 0; 1 1 0 0; 0 0 0 1; 0 1 1 0; 1 1 0 0; 0 0 0 1; 0 1 1 0; 1 1 1 0; 1 1 0 0; 0 1 0 1; 0 1 1 0; 1 1 0 1; 0 1 0 1; 0 1 1 1; 1 1 1 1; 1 1 1 1; 1 1 1 0; 1 1 1 1; 1 1 1 1; 1 1 1 0; 1 1 1 1; 1 1 1 1; 1 1 0 1; 0 1 0 1; 0 1 1 1; 1 0 0 1; 0 1 0 1; 0 0 1 1; 1 0 1 1; 1 0 1 1; 1 0 1 1; 1 0 1 1; 1 0 1 1; 1 0 1 1; 1 0 1 1; 1 0 1 1; 1 0 0 1; 0 1 0 1; 0 0 1 1; 0 0 1 0; 1 1 1 1; 1 0 1 0; 1 0 1 0; 1 0 1 0; 1 0 1 0; 1 0 1 0; 1 0 1 0; 1 0 1 0; 1 0 1 0; 1 0 1 0; 1 0 1 0; 1 1 1 1; 1 0 0 0; 1 1 0 0; 0 0 0 1; 0 1 1 0; 1 1 1 0; 1 1 1 0; 1 1 1 0; 1 1 1 0; 1 1 1 0; 1 1 1 0; 1 1 1 0; 1 1 1 0; 1 1 0 0; 0 0 0 1; 0 1 1 0];
            
        case 'spiral-6x6-ccw',
            maze.R            = 6;
            maze.C            = 6;
            maze.startRow     = 1;
            maze.startCol     = 1;
            maze.exitRow      = 4;
            maze.exitCol      = 4;
            maze.correctMoves = 'DDDDDRDDDDRRLDDRRRLLDSRRLLUUURLUUUUU';
            maze.cellLabels   = [ -1 0 0 0 0 1 1 0 0 0 1 0 0 1 0 1 0 0 0 0 1 -2 0 0 0 0 0 0 1 0 1 0 0 0 0 1];
            maze.adjacent     = [ 0 0 1 0; 1 0 1 0; 1 0 1 0; 1 0 1 0; 1 0 1 0; 1 1 0 0; 0 1 1 0; 1 0 1 0; 1 0 1 0; 1 0 1 0; 1 1 0 0; 0 1 0 1; 0 1 0 1; 0 1 1 0; 1 0 1 0; 1 1 0 0; 0 1 0 1; 0 1 0 1; 0 1 0 1; 0 1 0 1; 0 0 1 0; 1 0 0 1; 0 1 0 1; 0 1 0 1; 0 1 0 1; 0 0 1 1; 1 0 1 0; 1 0 1 0; 1 0 0 1; 0 1 0 1; 0 0 1 1; 1 0 1 0; 1 0 1 0; 1 0 1 0; 1 0 1 0; 1 0 0 1];
            
        case 'spiral-6x6-cw',
            maze.R            = 6;
            maze.C            = 6;
            maze.startRow     = 1;
            maze.startCol     = 1;
            maze.exitRow      = 4;
            maze.exitCol      = 4;
            maze.correctMoves = 'RRUUUURRRUULRRRSLLRRDSLLRDDDLLDDDDDL';
            maze.cellLabels   = [ -1 1 0 0 0 1 0 0 1 0 1 0 0 0 0 0 0 0 0 0 1 -2 0 0 0 1 0 0 1 0 1 0 0 0 0 1];
            maze.adjacent     = [ 0 1 0 0; 0 1 1 0; 1 0 1 0; 1 0 1 0; 1 0 1 0; 1 1 0 0; 0 1 0 1; 0 1 0 1; 0 1 1 0; 1 0 1 0; 1 1 0 0; 0 1 0 1; 0 1 0 1; 0 1 0 1; 0 1 0 1; 0 0 0 0; 0 1 0 1; 0 1 0 1; 0 1 0 1; 0 1 0 1; 0 0 1 1; 1 0 0 0; 0 1 0 1; 0 1 0 1; 0 1 0 1; 0 0 1 1; 1 0 1 0; 1 0 1 0; 1 0 0 1; 0 1 0 1; 0 0 1 1; 1 0 1 0; 1 0 1 0; 1 0 1 0; 1 0 1 0; 1 0 0 1];
            
        case 'evaluation',
            maze.R            = 16;
            maze.C            = 16;
            maze.startRow     = 1;
            maze.startCol     = 1;
            maze.exitRow      = 16;
            maze.exitCol      = 16;
            maze.correctMoves = '';
            maze.cellLabels   = [ 1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 1 0 0 0 0 2 0 0 0 0 2 0 0 0 0 1 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 1 0 0 0 0 2 0 0 0 0 2 0 0 0 0 1 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 -2];
            maze.adjacent     = [ 0 1 1 0; 1 0 1 0; 1 0 1 0; 1 0 1 0; 1 0 1 0; 1 1 1 0; 1 0 1 0; 1 0 1 0; 1 0 1 0; 1 0 1 0; 1 1 1 0; 1 0 1 0; 1 0 1 0; 1 0 1 0; 1 0 1 0; 1 1 0 0; 0 1 0 1; 0 1 1 0; 1 1 1 0; 1 1 1 0; 1 1 0 0; 0 1 0 1; 0 1 1 0; 1 1 1 0; 1 1 1 0; 1 1 0 0; 0 1 0 1; 0 1 1 0; 1 1 1 0; 1 1 1 0; 1 1 0 0; 0 1 0 1; 0 1 0 1; 0 1 1 1; 1 1 1 1; 1 1 1 1; 1 1 0 1; 0 1 0 1; 0 1 1 1; 1 1 1 1; 1 1 1 1; 1 1 0 1; 0 1 0 1; 0 1 1 1; 1 1 1 1; 1 1 1 1; 1 1 0 1; 0 1 0 1; 0 1 0 1; 0 1 1 1; 1 1 1 1; 1 1 1 1; 1 1 0 1; 0 1 0 1; 0 1 1 1; 1 1 1 1; 1 1 1 1; 1 1 0 1; 0 1 0 1; 0 1 1 1; 1 1 1 1; 1 1 1 1; 1 1 0 1; 0 1 0 1; 0 1 0 1; 0 0 1 1; 1 0 1 1; 1 0 1 1; 1 0 0 1; 0 1 0 1; 0 0 1 1; 1 0 1 1; 1 0 1 1; 1 0 0 1; 0 1 0 1; 0 0 1 1; 1 0 1 1; 1 0 1 1; 1 0 0 1; 0 1 0 1; 0 1 1 1; 1 0 1 0; 1 0 1 0; 1 0 1 0; 1 0 1 0; 1 1 1 1; 1 0 1 0; 1 0 1 0; 1 0 1 0; 1 0 1 0; 1 1 1 1; 1 0 1 0; 1 0 1 0; 1 0 1 0; 1 0 1 0; 1 1 0 1; 0 1 0 1; 0 1 1 0; 1 1 1 0; 1 1 1 0; 1 1 0 0; 0 1 0 1; 0 1 1 0; 1 1 1 0; 1 1 1 0; 1 1 0 0; 0 1 0 1; 0 1 1 0; 1 1 1 0; 1 1 1 0; 1 1 0 0; 0 1 0 1; 0 1 0 1; 0 1 1 1; 1 1 1 1; 1 1 1 1; 1 1 0 1; 0 1 0 1; 0 1 1 1; 1 1 1 1; 1 1 1 1; 1 1 0 1; 0 1 0 1; 0 1 1 1; 1 1 1 1; 1 1 1 1; 1 1 0 1; 0 1 0 1; 0 1 0 1; 0 1 1 1; 1 1 1 1; 1 1 1 1; 1 1 0 1; 0 1 0 1; 0 1 1 1; 1 1 1 1; 1 1 1 1; 1 1 0 1; 0 1 0 1; 0 1 1 1; 1 1 1 1; 1 1 1 1; 1 1 0 1; 0 1 0 1; 0 1 0 1; 0 0 1 1; 1 0 1 1; 1 0 1 1; 1 0 0 1; 0 1 0 1; 0 0 1 1; 1 0 1 1; 1 0 1 1; 1 0 0 1; 0 1 0 1; 0 0 1 1; 1 0 1 1; 1 0 1 1; 1 0 0 1; 0 1 0 1; 0 1 1 1; 1 0 1 0; 1 0 1 0; 1 0 1 0; 1 0 1 0; 1 1 1 1; 1 0 1 0; 1 0 1 0; 1 0 1 0; 1 0 1 0; 1 1 1 1; 1 0 1 0; 1 0 1 0; 1 0 1 0; 1 0 1 0; 1 1 0 1; 0 1 0 1; 0 1 1 0; 1 1 1 0; 1 1 1 0; 1 1 0 0; 0 1 0 1; 0 1 1 0; 1 1 1 0; 1 1 1 0; 1 1 0 0; 0 1 0 1; 0 1 1 0; 1 1 1 0; 1 1 1 0; 1 1 0 0; 0 1 0 1; 0 1 0 1; 0 1 1 1; 1 1 1 1; 1 1 1 1; 1 1 0 1; 0 1 0 1; 0 1 1 1; 1 1 1 1; 1 1 1 1; 1 1 0 1; 0 1 0 1; 0 1 1 1; 1 1 1 1; 1 1 1 1; 1 1 0 1; 0 1 0 1; 0 1 0 1; 0 1 1 1; 1 1 1 1; 1 1 1 1; 1 1 0 1; 0 1 0 1; 0 1 1 1; 1 1 1 1; 1 1 1 1; 1 1 0 1; 0 1 0 1; 0 1 1 1; 1 1 1 1; 1 1 1 1; 1 1 0 1; 0 1 0 1; 0 1 0 1; 0 0 1 1; 1 0 1 1; 1 0 1 1; 1 0 0 1; 0 1 0 1; 0 0 1 1; 1 0 1 1; 1 0 1 1; 1 0 0 1; 0 1 0 1; 0 0 1 1; 1 0 1 1; 1 0 1 1; 1 0 0 1; 0 1 0 1; 0 0 1 1; 1 0 1 0; 1 0 1 0; 1 0 1 0; 1 0 1 0; 1 0 1 1; 1 0 1 0; 1 0 1 0; 1 0 1 0; 1 0 1 0; 1 0 1 1; 1 0 1 0; 1 0 1 0; 1 0 1 0; 1 0 1 0; 1 0 0 1];
            
        case 'evaluation-13x13',
            maze.R            = 13;
            maze.C            = 13;
            maze.startRow     = 1;
            maze.startCol     = 1;
            maze.exitRow      = 13;
            maze.exitCol      = 13;
            maze.correctMoves = '';
            maze.cellLabels   = [ 1 0 0 0 1 0 0 0 1 0 0 0 1 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 1 0 0 0 2 0 0 0 2 0 0 0 1 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 1 0 0 0 2 0 0 0 2 0 0 0 1 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 1 0 0 0 1 0 0 0 1 0 0 0 -2];
            maze.adjacent     = [ 0 1 1 0; 1 0 1 0; 1 0 1 0; 1 0 1 0; 1 1 1 0; 1 0 1 0; 1 0 1 0; 1 0 1 0; 1 1 1 0; 1 0 1 0; 1 0 1 0; 1 0 1 0; 1 1 0 0; 0 1 0 1; 0 1 1 0; 1 1 1 0; 1 1 0 0; 0 1 0 1; 0 1 1 0; 1 1 1 0; 1 1 0 0; 0 1 0 1; 0 1 1 0; 1 1 1 0; 1 1 0 0; 0 1 0 1; 0 1 0 1; 0 1 1 1; 1 1 1 1; 1 1 0 1; 0 1 0 1; 0 1 1 1; 1 1 1 1; 1 1 0 1; 0 1 0 1; 0 1 1 1; 1 1 1 1; 1 1 0 1; 0 1 0 1; 0 1 0 1; 0 0 1 1; 1 0 1 1; 1 0 0 1; 0 1 0 1; 0 0 1 1; 1 0 1 1; 1 0 0 1; 0 1 0 1; 0 0 1 1; 1 0 1 1; 1 0 0 1; 0 1 0 1; 0 1 1 1; 1 0 1 0; 1 0 1 0; 1 0 1 0; 1 1 1 1; 1 0 1 0; 1 0 1 0; 1 0 1 0; 1 1 1 1; 1 0 1 0; 1 0 1 0; 1 0 1 0; 1 1 0 1; 0 1 0 1; 0 1 1 0; 1 1 1 0; 1 1 0 0; 0 1 0 1; 0 1 1 0; 1 1 1 0; 1 1 0 0; 0 1 0 1; 0 1 1 0; 1 1 1 0; 1 1 0 0; 0 1 0 1; 0 1 0 1; 0 1 1 1; 1 1 1 1; 1 1 0 1; 0 1 0 1; 0 1 1 1; 1 1 1 1; 1 1 0 1; 0 1 0 1; 0 1 1 1; 1 1 1 1; 1 1 0 1; 0 1 0 1; 0 1 0 1; 0 0 1 1; 1 0 1 1; 1 0 0 1; 0 1 0 1; 0 0 1 1; 1 0 1 1; 1 0 0 1; 0 1 0 1; 0 0 1 1; 1 0 1 1; 1 0 0 1; 0 1 0 1; 0 1 1 1; 1 0 1 0; 1 0 1 0; 1 0 1 0; 1 1 1 1; 1 0 1 0; 1 0 1 0; 1 0 1 0; 1 1 1 1; 1 0 1 0; 1 0 1 0; 1 0 1 0; 1 1 0 1; 0 1 0 1; 0 1 1 0; 1 1 1 0; 1 1 0 0; 0 1 0 1; 0 1 1 0; 1 1 1 0; 1 1 0 0; 0 1 0 1; 0 1 1 0; 1 1 1 0; 1 1 0 0; 0 1 0 1; 0 1 0 1; 0 1 1 1; 1 1 1 1; 1 1 0 1; 0 1 0 1; 0 1 1 1; 1 1 1 1; 1 1 0 1; 0 1 0 1; 0 1 1 1; 1 1 1 1; 1 1 0 1; 0 1 0 1; 0 1 0 1; 0 0 1 1; 1 0 1 1; 1 0 0 1; 0 1 0 1; 0 0 1 1; 1 0 1 1; 1 0 0 1; 0 1 0 1; 0 0 1 1; 1 0 1 1; 1 0 0 1; 0 1 0 1; 0 0 1 1; 1 0 1 0; 1 0 1 0; 1 0 1 0; 1 0 1 1; 1 0 1 0; 1 0 1 0; 1 0 1 0; 1 0 1 1; 1 0 1 0; 1 0 1 0; 1 0 1 0; 1 0 0 1];
            
        case 'evaluation-13x10',
            maze.R            = 10;
            maze.C            = 13;
            maze.startRow     = 1;
            maze.startCol     = 1;
            maze.exitRow      = 10;
            maze.exitCol      = 13;
            maze.correctMoves = '';
            maze.cellLabels   = [ -1 0 0 1 0 0 1 0 0 1 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 1 0 0 2 0 0 2 0 0 1 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 1 0 0 2 0 0 2 0 0 1 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 1 0 0 1 0 0 1 0 0 -2];
            maze.adjacent     = [ 0 1 1 0; 1 0 1 0; 1 0 1 0; 1 1 1 0; 1 0 1 0; 1 0 1 0; 1 1 1 0; 1 0 1 0; 1 0 1 0; 1 1 0 0; 0 1 0 1; 0 1 1 0; 1 1 0 0; 0 1 0 1; 0 1 1 0; 1 1 0 0; 0 1 0 1; 0 1 1 0; 1 1 0 0; 0 1 0 1; 0 1 0 1; 0 1 1 1; 1 1 0 1; 0 1 0 1; 0 1 1 1; 1 1 0 1; 0 1 0 1; 0 1 1 1; 1 1 0 1; 0 1 0 1; 0 1 0 1; 0 0 1 1; 1 0 0 1; 0 1 0 1; 0 0 1 1; 1 0 0 1; 0 1 0 1; 0 0 1 1; 1 0 0 1; 0 1 0 1; 0 1 1 1; 1 0 1 0; 1 0 1 0; 1 1 1 1; 1 0 1 0; 1 0 1 0; 1 1 1 1; 1 0 1 0; 1 0 1 0; 1 1 0 1; 0 1 0 1; 0 1 1 0; 1 1 0 0; 0 1 0 1; 0 1 1 0; 1 1 0 0; 0 1 0 1; 0 1 1 0; 1 1 0 0; 0 1 0 1; 0 1 0 1; 0 1 1 1; 1 1 0 1; 0 1 0 1; 0 1 1 1; 1 1 0 1; 0 1 0 1; 0 1 1 1; 1 1 0 1; 0 1 0 1; 0 1 0 1; 0 0 1 1; 1 0 0 1; 0 1 0 1; 0 0 1 1; 1 0 0 1; 0 1 0 1; 0 0 1 1; 1 0 0 1; 0 1 0 1; 0 1 1 1; 1 0 1 0; 1 0 1 0; 1 1 1 1; 1 0 1 0; 1 0 1 0; 1 1 1 1; 1 0 1 0; 1 0 1 0; 1 1 0 1; 0 1 0 1; 0 1 1 0; 1 1 0 0; 0 1 0 1; 0 1 1 0; 1 1 0 0; 0 1 0 1; 0 1 1 0; 1 1 0 0; 0 1 0 1; 0 1 0 1; 0 1 1 1; 1 1 0 1; 0 1 0 1; 0 1 1 1; 1 1 0 1; 0 1 0 1; 0 1 1 1; 1 1 0 1; 0 1 0 1; 0 1 0 1; 0 0 1 1; 1 0 0 1; 0 1 0 1; 0 0 1 1; 1 0 0 1; 0 1 0 1; 0 0 1 1; 1 0 0 1; 0 1 0 1; 0 0 1 1; 1 0 1 0; 1 0 1 0; 1 0 1 1; 1 0 1 0; 1 0 1 0; 1 0 1 1; 1 0 1 0; 1 0 1 0; 1 0 0 1;];
            
        case 'evaluation-maze-16x10',
            maze.R            = 10;
            maze.C            = 16;
            maze.startRow     = 1;
            maze.startCol     = 1;
            maze.exitRow      = 8;
            maze.exitCol      = 14;
            maze.correctMoves = '';
            maze.cellLabels   = [ -1 0 0 1 0 0 1 0 0 1 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 1 0 0 2 0 0 2 0 0 1 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 1 0 0 2 0 0 2 0 0 1 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 1 0 0 2 0 0 2 0 0 1 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 1 0 0 2 0 0 2 0 0 1 0 0 0 0 0 0 0 -2 1 0 0 0 0 0 0 0 0 1 1 1 1 0 0 1 0 0 1 0 0 1];
            maze.adjacent     = [ 0 1 1 0; 1 0 1 0; 1 0 1 0; 1 1 1 0; 1 0 1 0; 1 0 1 0; 1 1 1 0; 1 0 1 0; 1 0 1 0; 1 1 0 0; 0 1 0 1; 0 1 1 0; 1 1 0 0; 0 1 0 1; 0 1 1 0; 1 1 0 0; 0 1 0 1; 0 1 1 0; 1 1 0 0; 0 1 0 1; 0 1 0 1; 0 0 1 1; 1 0 0 1; 0 1 0 1; 0 0 1 1; 1 0 0 1; 0 1 0 1; 0 0 1 1; 1 0 0 1; 0 1 0 1; 0 1 1 1; 1 0 1 0; 1 0 1 0; 1 1 1 1; 1 0 1 0; 1 0 1 0; 1 1 1 1; 1 0 1 0; 1 0 1 0; 1 1 0 1; 0 1 0 1; 0 1 1 0; 1 1 0 0; 0 1 0 1; 0 1 1 0; 1 1 0 0; 0 1 0 1; 0 1 1 0; 1 1 0 0; 0 1 0 1; 0 1 0 1; 0 0 1 1; 1 0 0 1; 0 1 0 1; 0 0 1 1; 1 0 0 1; 0 1 0 1; 0 0 1 1; 1 0 0 1; 0 1 0 1; 0 1 1 1; 1 0 1 0; 1 0 1 0; 1 1 1 1; 1 0 1 0; 1 0 1 0; 1 1 1 1; 1 0 1 0; 1 0 1 0; 1 1 0 1; 0 1 0 1; 0 1 1 0; 1 1 0 0; 0 1 0 1; 0 1 1 0; 1 1 0 0; 0 1 0 1; 0 1 1 0; 1 1 0 0; 0 1 0 1; 0 1 0 1; 0 0 1 1; 1 0 0 1; 0 1 0 1; 0 0 1 1; 1 0 0 1; 0 1 0 1; 0 0 1 1; 1 0 0 1; 0 1 0 1; 0 1 1 1; 1 0 1 0; 1 0 1 0; 1 1 1 1; 1 0 1 0; 1 0 1 0; 1 1 1 1; 1 0 1 0; 1 0 1 0; 1 1 0 1; 0 1 0 1; 0 1 1 0; 1 1 0 0; 0 1 0 1; 0 1 1 0; 1 1 0 0; 0 1 0 1; 0 1 1 0; 1 1 0 0; 0 1 0 1; 0 1 0 1; 0 0 1 1; 1 0 0 1; 0 1 0 1; 0 0 1 1; 1 0 0 1; 0 1 0 1; 0 0 1 1; 1 0 0 1; 0 1 0 1; 0 1 1 1; 1 0 1 0; 1 0 1 0; 1 1 1 1; 1 0 1 0; 1 0 1 0; 1 1 1 1; 1 0 1 0; 1 0 1 0; 1 1 0 1; 0 1 0 1; 0 1 1 0; 1 1 0 0; 0 1 0 1; 0 1 1 0; 1 1 0 0; 0 1 0 1; 0 1 1 0; 1 1 0 0; 0 1 0 1; 0 1 0 1; 0 0 1 1; 1 0 0 1; 0 1 0 1; 0 0 1 1; 1 0 0 1; 0 1 0 1; 0 0 1 1; 1 0 1 1; 1 1 0 1; 0 0 1 1; 1 0 1 0; 1 0 1 0; 1 0 1 1; 1 0 1 0; 1 0 1 0; 1 0 1 1; 1 0 1 0; 1 0 1 0; 1 0 0 1;];
            
        case 'evaluation-maze-9x7',
            maze.R            = 7;
            maze.C            = 9;
            maze.startRow     = 1;
            maze.startCol     = 1;
            maze.exitRow      = 6;
            maze.exitCol      = 8;
            maze.correctMoves = '';
            maze.cellLabels   = [ -1 0 1 0 1 0 1 0 0 0 0 0 0 0 1 0 2 0 2 0 1 0 0 0 0 0 0 0 1 0 2 0 2 0 1 0 0 0 0 0 0 0 1 0 2 0 2 0 1 0 0 0 0 0 -2 0 1 0 1 0 1 1 1];
            maze.adjacent     = [ 0 1 1 0; 1 0 1 0; 1 1 1 0; 1 0 1 0; 1 1 1 0; 1 0 1 0; 1 1 0 0; 0 1 0 1; 0 0 0 0; 0 1 0 1; 0 0 0 0; 0 1 0 1; 0 0 0 0; 0 1 0 1; 0 1 1 1; 1 0 1 0; 1 1 1 1; 1 0 1 0; 1 1 1 1; 1 0 1 0; 1 1 0 1; 0 1 0 1; 0 0 0 0; 0 1 0 1; 0 0 0 0; 0 1 0 1; 0 0 0 0; 0 1 0 1; 0 1 1 1; 1 0 1 0; 1 1 1 1; 1 0 1 0; 1 1 1 1; 1 0 1 0; 1 1 0 1; 0 1 0 1; 0 0 0 0; 0 1 0 1; 0 0 0 0; 0 1 0 1; 0 0 0 0; 0 1 0 1; 0 1 1 1; 1 0 1 0; 1 1 1 1; 1 0 1 0; 1 1 1 1; 1 0 1 0; 1 1 0 1; 0 1 0 1; 0 0 0 0; 0 1 0 1; 0 0 0 0; 0 1 0 1; 0 1 0 0; 0 1 0 1; 0 0 1 1; 1 0 1 0; 1 0 1 1; 1 0 1 0; 1 0 1 1; 1 0 1 1; 1 0 0 1;];
            
    end
    if ~isempty( maze.correctMoves ),
        maze.correctMoves( maze.correctMoves == 'L' ) = '1';
        maze.correctMoves( maze.correctMoves == 'U' ) = '2';
        maze.correctMoves( maze.correctMoves == 'R' ) = '3';
        maze.correctMoves( maze.correctMoves == 'D' ) = '4';
        maze.correctMoves( maze.correctMoves == 'S' ) = '0';
    end
    
end % of GENERATEMAZE() function

%--------------------------------------------------------------------------------------------
function maze = labelMaze( maze )
    nCells = maze.R*maze.C;
    % label "special" cells
    maze.cellLabels = ones( nCells, 1);
    for i = 1:nCells,
        if isequal( maze.adjacent(i,:), [1 0 1 0] ) || isequal( maze.adjacent(i,:), [0 1 0 1]),
            maze.cellLabels(i) = 0;
        end
    end
end % of LABELMAZE() function

%--------------------------------------------------------------------------------------------
function resultImg = blendIn( whatImg, whereImg, alpha )
    if nargin < 3, alpha = 1; end
    tempImg = double( imresize( whatImg, [size( whereImg, 1 ) size( whereImg, 2 )] ) );
    alphaMask = alpha*repmat( tempImg(:,:,end) / 255, [1 1 3] );
    resultImg = (1-alphaMask) .* double( whereImg ) + alphaMask .* tempImg(:,:,1:end-1);
end % of BLENDIN() function

%--------------------------------------------------------------------------------------------
function controlLevel = controlLevelValidationGUI()
    controlLevel = 0.5;
    hDialog = figure(...
        'Units', 'characters',...
        'Color', [0.831372549019608 0.815686274509804 0.784313725490196],...
        'MenuBar', 'none',...
        'Name', 'Please evaluate your level of achieved control (over The Maze game)',...
        'NumberTitle', 'off',...
        'Position', [100 50 200 9],...
        'Resize', 'off',...
        'Tag', 'clvFig',...
        'Visible', 'on'...
        );
    
    hSlider = uicontrol(...
        'Parent', hDialog,...
        'Units','characters',...
        'BackgroundColor',[0.9 0.9 0.9],...
        'Position', [19.8 6.15384615384615 160.2 1.61538461538462], ...
        'String', {'Slider'},...
        'Min', 0, 'Max', 1, 'Value', controlLevel, ...
        'Callback', @updateValue, ...
        'Style', 'slider',...
        'Tag', 'slider' );
    
    h3 = uicontrol(...
        'Parent', hDialog,...
        'Units','characters',...
        'Callback', @submitButtonCallback, ...
        'Position', [3.6 2.46153846153846 192.2 2.23076923076923], ...
        'String','Submit' );
    
    h4 = uicontrol(...
        'Parent', hDialog,...
        'Units','characters',...
        'FontSize', 10,...
        'FontWeight','bold',...
        'ForegroundColor', [0.5 0 0],...
        'HorizontalAlignment','right',...
        'Position', [0 6.15384615384615 18 1.61538461538462],...
        'String','No control',...
        'Style','text' );
    
    h5 = uicontrol(...
        'Parent', hDialog,...
        'Units','characters',...
        'FontSize', 10,...
        'FontWeight','bold',...
        'ForegroundColor',[0 0.5 0],...
        'HorizontalAlignment','left',...
        'Position',[181 6.15384615384615 16.2 1.61538461538462],...
        'String','Full control',...
        'Style','text' );
    
    set( findobj( hDialog ), 'KeyPressFcn', @guiKeyPressFunction );
    uiwait( hDialog );
    
    %-----------------------------------------------------------------------
    function guiKeyPressFunction( ~, eventdata, ~ )
        if isstruct( eventdata ),
            key = eventdata.Character;
        else
            key = get( gcbf, 'CurrentCharacter' );
        end
        switch key,
            case 13,
                submitButtonCallback( gcbo, eventdata );
            case 27,
                controlLevel = nan;
                delete( gcbf );
            case {28,31},
                controlLevel = max( 0, get( hSlider, 'Value' ) - 0.01 );
                set( hSlider, 'Value', controlLevel );
            case {29,30},
                controlLevel = min( 1, get( hSlider, 'Value' ) + 0.01 );
                set( hSlider, 'Value', controlLevel );
        end
    end % of GUIKEYPRESSFUNCTION() nested function
    %---------------------------------------------------------------
    function submitButtonCallback( ~, ~ )
%         controlLevel = get( hSlider, 'Value' )
        close( gcbf );        
    end % of SUBMITBUTTONCALLBACK() nested function
    %---------------------------------------------------------------
    function updateValue( ~, ~ )
        controlLevel = get( hSlider, 'Value' );
    end % of UPDATEVALUE() nested function
end % of CONTROLLEVELVALIDATIONGUI() function

%---------------------------------------------------------------
function cs = compactString( s )
    cs = strtrim( s );
    cs = regexprep( cs, '\s+', ' ' );
end % of COMPACTSTRING() function

%---------------------------------------------------------------
function wait_for_message(con, message, skip_all_others)
    if nargin < 3
        skip_all_others = 0;
    end
   
    while true
        response = strtrim(pnet(con, 'readline'));
        if ~strcmpi(response, message)
            if ~skip_all_others
                sca;
                pnet(con, 'close');
                error('expected message: %s\nresponse: %s\n', message, response);
            end
        else
            return;
        end
    end
end % of WAIT_FOR_MESSAGE() function

%---------------------------------------------------------------
function tokens = tokenize_message(con)
        
    % Regular expression that uses named tokens to parse a message
    protocol_regexp = ['(?<plain>[^-\d\."][^"\s$]+)(?:\s+|$)|', ...  % Plain string, should not start with a number, '-' or '.' (use quoted string for that)
                       '"(?<quoted>(:?\\.|[^"\\])*)"(?:\s+|$)|', ... % Quoted string allowing whatever between quotes (allow for escaping of quotes)
                       '(?<int>-?\d+)(?:\s+|$)|', ...                % Integer value, starts with optional '-', then only digits
                       '(?<float>-?\d*.\d+)(?:\s+|$)'];              % Floating point value, starts with optional '-', optional digits, '.' and then only digits
    matches = regexp(pnet(con, 'readline'), protocol_regexp, 'names');
    tokens = cell(1, length(matches));

    % Loop over each match and determine data type
    for i = 1:length(matches)
        if ~isempty(matches(i).plain)
            % Plain string
            tokens{i} = matches(i).plain;
        elseif ~isempty(matches(i).quoted)
            % Quoted string. Quotes have been removed by the regexp,
            % but we still need to deal with the \" and \\ cases
            tokens{i} = strrep(matches(i).quoted, '\"', '"');
            tokens{i} = strrep(tokens{i}, '\\', '\');
        elseif ~isempty(matches(i).int)
            % Integer value
            tokens{i} = str2double(matches(i).int);
        elseif ~isempty(matches(i).float)
            % Floating point value
            tokens{i} = str2double(matches(i).float);
        end
    end
end % of TOKENIZE_MESSAGE() function