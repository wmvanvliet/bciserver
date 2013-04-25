function myBarrier( con )

    if nargin() == 0,
        con = 0;
    end
    
    defaultBarrierMessage = 'barrier';
    logThis( 'Barrier has been reached. Waiting for the rest threads... ' )
    pnet( con, 'printf', '%s\n', defaultBarrierMessage );
    barrierMessage = '';
    
    while ~strcmpi( barrierMessage, defaultBarrierMessage ),
        barrierMessage = pnet( con, 'readline', 1024 );
    end % of barrier waiting loop
    
end % of function MYBARRIER
